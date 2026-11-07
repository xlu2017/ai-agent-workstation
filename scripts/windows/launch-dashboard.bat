@echo off
REM launch-dashboard.bat
REM Quick launcher - opens SSH tunnel and dashboard in one click.
REM Requires: SSH key at %USERPROFILE%\.ssh\workstation_key

REM Required: set SERVER to your workstation IP or Tailscale hostname.
set SERVER=<server-ip>
if "%SERVER%"=="<server-ip>" (
    echo ERROR: Edit this file and set SERVER to your workstation IP or Tailscale hostname.
    pause
    exit /b 1
)

echo === Workstation Dashboard ===
echo.

if not exist "%USERPROFILE%\.ssh\workstation_key" (
    echo ERROR: SSH key not found at %USERPROFILE%\.ssh\workstation_key
    echo Copy your private key there or edit this script.
    pause
    exit /b 1
)

echo Starting SSH tunnel...
start /b ssh -i "%USERPROFILE%\.ssh\workstation_key" -N -L 9877:localhost:9877 -L 9876:localhost:9876 -o ServerAliveInterval=30 -o StrictHostKeyChecking=no agent@%SERVER%

timeout /t 3 /nobreak >nul

echo Opening browser...
start http://localhost:9877

echo.
echo Dashboard: http://localhost:9877
echo Press any key to close tunnel and exit.
pause >nul

REM Kill SSH tunnels
taskkill /f /im ssh.exe 2>nul
echo Tunnel closed.
