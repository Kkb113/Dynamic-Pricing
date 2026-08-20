$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"
$pythonCommand = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonCommand -PathType Leaf)) {
    $pythonCommand = "python"
}
$env:PYTHONPATH = Join-Path $repoRoot "src"

$backend = $null
$frontend = $null
try {
    $backend = Start-Process -WindowStyle Hidden -FilePath $pythonCommand -ArgumentList @("-m", "pricing_api") -WorkingDirectory $repoRoot -PassThru
    $frontend = Start-Process -WindowStyle Hidden -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1") -WorkingDirectory $frontendRoot -PassThru
    Write-Host "FastAPI: http://127.0.0.1:8000"
    Write-Host "React:   http://127.0.0.1:5173"
    Write-Host "Press Ctrl+C here to stop both local processes."
    Wait-Process -Id $frontend.Id
}
finally {
    foreach ($process in @($frontend, $backend)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
