"""Best-effort local Windows alerts; persistent in-app records remain authoritative."""
import asyncio
import base64
import os
from loguru import logger


async def notify_desktop(title,message):
    if os.name!='nt':
        return False
    # Base64 environment values prevent shell interpretation of website text.
    script='''Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$titleText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:FLIGHT_ALERT_TITLE))
$bodyText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:FLIGHT_ALERT_BODY))
$icon = New-Object System.Windows.Forms.NotifyIcon
try {
  $icon.Icon = [System.Drawing.SystemIcons]::Information
  $icon.Visible = $true
  $icon.ShowBalloonTip(10000, $titleText, $bodyText, [System.Windows.Forms.ToolTipIcon]::Info)
  Start-Sleep -Seconds 10
} finally { $icon.Dispose() }
'''
    process=None
    try:
        process=await asyncio.create_subprocess_exec('powershell.exe','-NoProfile','-WindowStyle','Hidden','-Command',script,
            env={**os.environ,'FLIGHT_ALERT_TITLE':base64.b64encode(title[:60].encode()).decode(),
                 'FLIGHT_ALERT_BODY':base64.b64encode(message[:240].encode()).decode()},
            stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000)
        async with asyncio.timeout(20):
            return await process.wait()==0
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning('Desktop alert unavailable: {}. The alert is saved in Red Room.',type(exc).__name__)
        return False
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
