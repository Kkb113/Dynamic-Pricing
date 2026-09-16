$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path (Join-Path $repoRoot ".phase4-runtime") "owned-processes.json"
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Output "No owned local Phase 4 processes recorded."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.schema_version -ne "phase4.owned-processes.v1" -or $state.repo_root -ne $repoRoot -or $state.launch_mode -ne "direct_backend_and_vite_root_processes") { throw "OWNED_STATE_INVALID" }
try {
    $backendPort = [int]$state.backend_port
    $frontendPort = [int]$state.frontend_port
    if ($backendPort -lt 1 -or $backendPort -gt 65535 -or $frontendPort -lt 1 -or $frontendPort -gt 65535 -or $backendPort -eq $frontendPort) { throw "OWNED_STATE_PORTS_INVALID" }
} catch { throw "OWNED_STATE_PORTS_INVALID" }

function Get-ProcessIdentity([int]$processId, [string]$expectedCommandLine) {
    try {
        $record = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        if ($null -eq $record) { throw "PROCESS_NOT_FOUND_$processId" }
        if ([string]::IsNullOrWhiteSpace([string]$record.ExecutablePath) -or [string]::IsNullOrWhiteSpace([string]$record.CommandLine) -or [string]::IsNullOrWhiteSpace([string]$record.CreationDate)) { throw "PROCESS_IDENTITY_UNAVAILABLE" }
         $created = [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$record.CreationDate).ToUniversalTime().ToString("o")
         return [pscustomobject]@{ pid = [int]$record.ProcessId; executable = [string]$record.ExecutablePath; command_line = [string]$record.CommandLine; command_line_source = "wmi"; creation_time = $created }
    } catch {
        try { $process = Get-Process -Id $processId -ErrorAction Stop; $path = [string]$process.Path; $start = $process.StartTime.ToUniversalTime().ToString("o") } catch { throw "PROCESS_IDENTITY_UNAVAILABLE" }
        if ([string]::IsNullOrWhiteSpace($path) -or [string]::IsNullOrWhiteSpace($start) -or [string]::IsNullOrWhiteSpace($expectedCommandLine)) { throw "PROCESS_IDENTITY_UNAVAILABLE" }
        return [pscustomobject]@{ pid = $processId; executable = $path; command_line = $expectedCommandLine; command_line_source = "launcher_expected"; creation_time = $start }
    }
}

function Normalize-CreationTime($value) {
    if ($value -is [DateTime]) { return $value.ToUniversalTime().ToString("o") }
    try { return ([DateTimeOffset]::Parse([string]$value, [Globalization.CultureInfo]::InvariantCulture)).UtcDateTime.ToString("o") }
    catch { return [string]$value }
}

# Validate every identity before stopping anything.  PID reuse, command-line
# drift, and executable drift are treated as a hard stop, never as permission
# to broaden cleanup.
$validated = @()
foreach ($record in @($state.processes)) {
    try { $current = Get-ProcessIdentity ([int]$record.pid) ([string]$record.command_line) } catch { continue }
    if ($current.executable -ne [string]$record.executable -or $current.creation_time -ne (Normalize-CreationTime $record.creation_time)) { throw "PROCESS_IDENTITY_MISMATCH_$($record.pid)" }
    if ($record.command_line_source -eq "wmi" -and ($current.command_line_source -ne "wmi" -or $current.command_line -ne [string]$record.command_line)) { throw "PROCESS_IDENTITY_MISMATCH_$($record.pid)" }
    $validated += [pscustomobject]@{ pid = [int]$record.pid; parent_pid = [int]$record.parent_pid; depth = [int]$record.depth; identity = $current }
}

# Children first ensures Vite is stopped even when npm/cmd is only a wrapper.
foreach ($record in ($validated | Sort-Object depth -Descending)) {
    try { Stop-Process -Id $record.pid -ErrorAction Stop } catch { }
}
Remove-Item -LiteralPath $statePath -Force -ErrorAction Stop
Write-Output "Owned local Phase 4 processes stopped on ports $backendPort and $frontendPort."
