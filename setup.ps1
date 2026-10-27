param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Push-Location $projectRoot
try {
    & $Python -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14), 'Use Python 3.12 or 3.13'"
    if ($LASTEXITCODE -ne 0) { throw 'A working Python 3.12 or 3.13 is required; pass its path using -Python.' }
    if (-not (Test-Path -LiteralPath 'backend/.venv/Scripts/python.exe')) {
        & $Python -m venv backend/.venv
        if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
    }
    & backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installing Python dependencies failed.' }
    & backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-google.txt
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Optional Google reader unavailable. Google searches will use the browser fallback.' }
    & backend/.venv/Scripts/python.exe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Installing Chromium failed.' }
    Push-Location frontend
    try {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Installing frontend dependencies failed.' }
    } finally { Pop-Location }
    Write-Host 'Setup complete. Run ./start.ps1 to open Flight Finder.'
} finally { Pop-Location }
