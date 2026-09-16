$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $repoRoot -Parent) ".venv\Scripts\python.exe")
)
$pythonCommand = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace([string]$pythonCommand)) { $pythonCommand = "python" }
$env:PYTHONPATH = Join-Path $repoRoot "src"
& $pythonCommand -m pricing_api.preflight
exit $LASTEXITCODE
