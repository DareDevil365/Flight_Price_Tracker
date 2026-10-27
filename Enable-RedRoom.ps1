param([switch]$Disable)
$ErrorActionPreference = 'Stop'
$taskName = 'Flight Finder Red Room'
if ($Disable) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host 'Red Room automatic startup disabled. Existing app processes are unaffected.'
    exit
}
$runner = Join-Path $PSScriptRoot 'red-room-background.ps1'
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'backend/.venv/Scripts/python.exe'))) { throw 'Run setup.ps1 first.' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"')
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Check saved flight requests while this Windows account is logged in. Stores alerts locally; never purchases tickets.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host 'Red Room background startup enabled. Use ./Enable-RedRoom.ps1 -Disable to remove it.'
