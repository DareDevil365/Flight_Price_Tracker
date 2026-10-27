$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot 'backend/.venv/Scripts/python.exe'
while ($true) {
    $backendReady = $false
    try { $backendReady = (Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2).service -eq 'flight-finder' } catch {}
    if (-not $backendReady) { break }
    Start-Sleep -Seconds 30
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Flight Finder runtime missing. Run setup.ps1.' }
$logFolder = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logFolder | Out-Null
# Hidden child, with this scheduled task waiting so restart policy can observe exit.
$process = Start-Process -FilePath $pythonPath -ArgumentList 'main.py' -WorkingDirectory (Join-Path $PSScriptRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logFolder 'red-room.stdout.log') -RedirectStandardError (Join-Path $logFolder 'red-room.stderr.log') -PassThru
$process.WaitForExit()
exit $process.ExitCode
