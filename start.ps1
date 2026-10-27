param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run ./setup.ps1 with a working Python 3.12 or 3.13 first.' }
$logFolder = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $logFolder | Out-Null
$backendReady = $false
try { $backendReady = (Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2).service -eq 'flight-finder' } catch {}
if (-not $backendReady) {
    Start-Process -FilePath $pythonPath -ArgumentList 'main.py' -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logFolder 'backend.stdout.log') -RedirectStandardError (Join-Path $logFolder 'backend.stderr.log') | Out-Null
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $backendReady = (Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 1).service -eq 'flight-finder' } catch {}
        if ($backendReady) { break }
    }
    if (-not $backendReady) { throw 'Backend did not start. See logs/backend.stderr.log; check whether port 8765 is occupied.' }
}
$frontendReady = $false
try { $frontendReady = (Invoke-WebRequest 'http://127.0.0.1:5173' -TimeoutSec 2).Content -match '<title>Flight Finder</title>' } catch {}
if (-not $frontendReady) {
    $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
    $frontendLaunch = '""' + $npmCommand + '" run dev -- --host 127.0.0.1 --port 5173 --strictPort"'
    Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/s','/c',$frontendLaunch -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logFolder 'frontend.stdout.log') -RedirectStandardError (Join-Path $logFolder 'frontend.stderr.log') | Out-Null
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $frontendReady = (Invoke-WebRequest 'http://127.0.0.1:5173' -TimeoutSec 1).Content -match '<title>Flight Finder</title>' } catch {}
        if ($frontendReady) { break }
    }
    if (-not $frontendReady) { throw 'Frontend did not start. See logs/frontend.stderr.log; check whether port 5173 is occupied.' }
}
Write-Host 'Flight Finder: http://127.0.0.1:5173'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }
