$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $repoRoot -Parent) ".venv\Scripts\python.exe")
)
$pythonCommand = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace([string]$pythonCommand)) { $pythonCommand = "python" }
$env:PYTHONPATH = Join-Path $repoRoot "src"

Write-Output "Installing pinned frontend dependencies with npm ci..."
Push-Location $frontendRoot
try {
    npm ci
    npm run lint
    npm run typecheck
    npm test -- --run
    npm run build
} finally { Pop-Location }

Write-Output "Checking editable Python runtime..."
& $pythonCommand -m pip install -e "." --no-deps
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonCommand -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonCommand -m pricing_api.preflight
exit $LASTEXITCODE
