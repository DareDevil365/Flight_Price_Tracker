# Flight Finder automatic startup: ON / OFF

These options control the backend's automatic startup when you log in to Windows. Your saved flight requests are retained.

## If you are using Command Prompt (CMD)

A prompt like `C:\Users\...>` is Command Prompt. Calling a `.ps1` file directly there may open it in Notepad instead of executing it. Use these commands from the Flight Finder project folder. Copy only the command line, not the Markdown backticks or the language label.

OFF:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Enable-RedRoom.ps1" -Disable
```

ON:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Enable-RedRoom.ps1"
```

To reach the project folder from any other CMD directory:

```cmd
cd /d "%USERPROFILE%\Desktop\My Projects\Flight Finder"
```

## Where to run the commands

Open PowerShell. You do not have to be in your home directory. First go to the Flight Finder project folder:

```powershell
Set-Location "$env:USERPROFILE\Desktop\My Projects\Flight Finder"
```

Run the following commands from that project folder, not from the `Startup Controls` folder.

## 1. Turn automatic startup ON

```powershell
.\Enable-RedRoom.ps1
```

This enables the Windows login task and starts it now. It runs the backend for saved flight monitoring; it does not open the frontend.

## 2. Turn automatic startup OFF

```powershell
.\Enable-RedRoom.ps1 -Disable
```

This removes the Windows login task, so it will not automatically start the backend on future logins. It does not stop a backend already running. After restarting the laptop, it stays off until you enable it again. Saved requests are not deleted.

## Alternatively: run from any directory

You can skip changing folders by using the script's full location.

ON:

```powershell
& "$env:USERPROFILE\Desktop\My Projects\Flight Finder\Enable-RedRoom.ps1"
```

OFF:

```powershell
& "$env:USERPROFILE\Desktop\My Projects\Flight Finder\Enable-RedRoom.ps1" -Disable
```

If you move the project, update the location in these commands.
