param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
if ($BackendPort -eq $FrontendPort) { throw "PORTS_MUST_DIFFER" }
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

# Phase 4 local launcher.  It owns exactly the two child PIDs it starts and
# never searches for or terminates unrelated Python/Node processes.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $repoRoot -Parent) ".venv\Scripts\python.exe")
)
$pythonCommand = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace([string]$pythonCommand)) { $pythonCommand = "python" }
$nodeCommand = $null
try { $nodeCommand = (Get-Command node.exe -ErrorAction Stop).Source } catch { throw "NODE_RUNTIME_UNAVAILABLE" }
$viteEntry = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) { throw "FRONTEND_DEPENDENCIES_MISSING" }
$env:PYTHONPATH = Join-Path $repoRoot "src"
$previousFastApiPort = [System.Environment]::GetEnvironmentVariable("FASTAPI_PORT", "Process")
$previousReactOrigin = [System.Environment]::GetEnvironmentVariable("REACT_ORIGIN", "Process")
$previousViteApiBaseUrl = [System.Environment]::GetEnvironmentVariable("VITE_API_BASE_URL", "Process")
$stateRoot = Join-Path $repoRoot ".phase4-runtime"
$statePath = Join-Path $stateRoot "owned-processes.json"

function Assert-PortFree([int]$port) {
    try {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
    } catch {
        # Some locked-down Windows images omit/deny Get-NetTCPConnection. A
        # real loopback bind is an equivalent fail-closed listener probe.
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $port)
            try { $listener.Start() } catch { throw "PORT_IN_USE_$port" }
            finally { $listener.Stop() }
            return
        } catch {
            if ($_.Exception.Message -eq "PORT_IN_USE_$port") { throw }
            throw "PORT_CHECK_UNAVAILABLE"
        }
    }
    if ($listeners.Count -gt 0) { throw "PORT_IN_USE_$port" }
}

function Get-ProcessIdentity([int]$processId, [string]$expectedCommandLine) {
    try {
        $record = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        if ($null -eq $record) { throw "PROCESS_NOT_FOUND_$processId" }
        if ([string]::IsNullOrWhiteSpace([string]$record.ExecutablePath) -or [string]::IsNullOrWhiteSpace([string]$record.CommandLine) -or [string]::IsNullOrWhiteSpace([string]$record.CreationDate)) { throw "PROCESS_IDENTITY_UNAVAILABLE" }
        $created = [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$record.CreationDate).ToUniversalTime().ToString("o")
        return [pscustomobject]@{
            pid = [int]$record.ProcessId
            parent_pid = [int]$record.ParentProcessId
            executable = [string]$record.ExecutablePath
            command_line = [string]$record.CommandLine
            command_line_source = "wmi"
            creation_time = $created
            depth = 0
        }
    } catch {
        # WMI command-line access is denied in some locked-down hosts. The
        # launcher owns direct root processes, so a PID + exact executable +
        # StartTime identity remains safe; expected args are retained as an
        # additional invariant and are never used to broaden cleanup.
        try { $process = Get-Process -Id $processId -ErrorAction Stop; $path = [string]$process.Path; $start = $process.StartTime.ToUniversalTime().ToString("o") } catch { throw "PROCESS_IDENTITY_UNAVAILABLE" }
        if ([string]::IsNullOrWhiteSpace($path) -or [string]::IsNullOrWhiteSpace($start) -or [string]::IsNullOrWhiteSpace($expectedCommandLine)) { throw "PROCESS_IDENTITY_UNAVAILABLE" }
        return [pscustomobject]@{
            pid = $processId
            parent_pid = 0
            executable = $path
            command_line = $expectedCommandLine
            command_line_source = "launcher_expected"
            creation_time = $start
            depth = 0
        }
    }
}

function Stop-OwnedIdentity($identity) {
    $current = Get-ProcessIdentity ([int]$identity.pid) ([string]$identity.command_line)
    if ($current.executable -ne $identity.executable -or $current.creation_time -ne $identity.creation_time) { throw "PROCESS_IDENTITY_MISMATCH_$($identity.pid)" }
    if ($identity.command_line_source -eq "wmi" -and ($current.command_line_source -ne "wmi" -or $current.command_line -ne $identity.command_line)) { throw "PROCESS_IDENTITY_MISMATCH_$($identity.pid)" }
    Stop-Process -Id ([int]$identity.pid) -ErrorAction Stop
}

function Get-DescendantIdentities([int]$rootPid, [string]$expectedCommandLine) {
    try { $all = @(Get-Process -ErrorAction Stop) } catch { throw "PROCESS_IDENTITY_UNAVAILABLE" }
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue([pscustomobject]@{ pid = $rootPid; depth = 0 })
    $seen = @{}
    $seen[$rootPid] = $true
    $found = @()
    while ($pending.Count -gt 0) {
        $parentNode = $pending.Dequeue()
        foreach ($process in $all) {
            if ($seen.ContainsKey([int]$process.Id)) { continue }
            if ($process.ProcessName -eq "conhost") { continue }
            try { $parentId = [int]$process.Parent.Id } catch { continue }
            if ($parentId -ne [int]$parentNode.pid) { continue }
            $identity = Get-ProcessIdentity ([int]$process.Id) $expectedCommandLine
            $identity.parent_pid = $parentId
            $identity.depth = [int]$parentNode.depth + 1
            $found += $identity
            $seen[[int]$process.Id] = $true
            $pending.Enqueue([pscustomobject]@{ pid = [int]$process.Id; depth = [int]$parentNode.depth + 1 })
        }
    }
    return $found
}

function Wait-Http([string]$url, [int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -in @(200, 503)) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-ListeningProcessId([int]$port) {
    try { $lines = @(netstat -ano) } catch { throw "PROCESS_IDENTITY_UNAVAILABLE" }
    foreach ($line in $lines) {
        if ($line -match ":$port\s+.*LISTENING\s+(\d+)\s*$") { return [int]$Matches[1] }
    }
    throw "PROCESS_IDENTITY_UNAVAILABLE"
}

Assert-PortFree $BackendPort
Assert-PortFree $FrontendPort
if (Test-Path -LiteralPath $statePath -PathType Leaf) { throw "OWNED_STATE_PRESENT" }
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$backend = $null
$frontend = $null
try {
    # These values are inherited by the two owned child processes only. They
    # are restored before this launcher returns to avoid mutating the caller's
    # shell environment.
    $env:FASTAPI_PORT = [string]$BackendPort
    $env:REACT_ORIGIN = $frontendUrl
    $env:VITE_API_BASE_URL = $backendUrl
    $backend = Start-Process -WindowStyle Hidden -FilePath $pythonCommand -ArgumentList @("-m", "pricing_api") -WorkingDirectory $repoRoot -PassThru
    $backendIdentity = Get-ProcessIdentity $backend.Id "$pythonCommand -m pricing_api"
    if (-not (Wait-Http "$backendUrl/api/v1/healthz" 30)) { throw "BACKEND_NOT_READY" }
    $backendListenPid = Get-ListeningProcessId $BackendPort
    $backendListenIdentity = if ($backendListenPid -eq $backendIdentity.pid) { $null } else { Get-ProcessIdentity $backendListenPid "$pythonCommand -m pricing_api" }
    $backendDescendants = @(Get-DescendantIdentities $backend.Id "$pythonCommand -m pricing_api")
    # Own Vite's real node process directly; npm/cmd wrappers are not kept in
    # the process tree and therefore cannot orphan the frontend on shutdown.
    $frontend = Start-Process -WindowStyle Hidden -FilePath $nodeCommand -ArgumentList @($viteEntry, "--host", "127.0.0.1", "--port", [string]$FrontendPort) -WorkingDirectory $frontendRoot -PassThru
    if (-not (Wait-Http "$frontendUrl/" 30)) { throw "FRONTEND_NOT_READY" }
    $frontendIdentity = Get-ProcessIdentity $frontend.Id "$nodeCommand $viteEntry --host 127.0.0.1 --port $FrontendPort"
    $frontendDescendants = @(Get-DescendantIdentities $frontend.Id "$nodeCommand $viteEntry --host 127.0.0.1 --port $FrontendPort")
    $processCandidates = @($backendIdentity) + @($backendListenIdentity) + $backendDescendants + @($frontendIdentity) + $frontendDescendants
    $uniqueProcesses = @{}
    foreach ($identity in $processCandidates) { if ($null -ne $identity -and -not $uniqueProcesses.ContainsKey([int]$identity.pid)) { $uniqueProcesses[[int]$identity.pid] = $identity } }
    $processes = @($uniqueProcesses.Values)
    [pscustomobject]@{
        schema_version = "phase4.owned-processes.v1"
        repo_root = $repoRoot
        created_utc = [DateTime]::UtcNow.ToString("o")
        launch_mode = "direct_backend_and_vite_root_processes"
        backend_port = $BackendPort
        frontend_port = $FrontendPort
        processes = $processes
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-Output "FastAPI: $backendUrl"
    Write-Output "React:   $frontendUrl"
    Write-Output "Owned process state: $statePath"
} catch {
    $cleanup = @()
    if ($null -ne $backendIdentity) { $cleanup += $backendIdentity }
    if ($null -ne $backendListenIdentity) { $cleanup += $backendListenIdentity }
    if ($null -ne $frontendIdentity) { $cleanup += $frontendIdentity }
    if ($null -ne $backend) {
        try { $cleanup += @(Get-DescendantIdentities $backend.Id "$pythonCommand -m pricing_api") } catch { }
    }
    if ($null -ne $frontend) {
        try { $cleanup += @(Get-DescendantIdentities $frontend.Id "$nodeCommand $viteEntry --host 127.0.0.1 --port $FrontendPort") } catch { }
    }
    foreach ($identity in ($cleanup | Sort-Object depth -Descending -Unique)) {
        try { Stop-OwnedIdentity $identity } catch { }
    }
    throw
} finally {
    if ($null -eq $previousFastApiPort) { Remove-Item Env:FASTAPI_PORT -ErrorAction SilentlyContinue } else { $env:FASTAPI_PORT = $previousFastApiPort }
    if ($null -eq $previousReactOrigin) { Remove-Item Env:REACT_ORIGIN -ErrorAction SilentlyContinue } else { $env:REACT_ORIGIN = $previousReactOrigin }
    if ($null -eq $previousViteApiBaseUrl) { Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue } else { $env:VITE_API_BASE_URL = $previousViteApiBaseUrl }
}
