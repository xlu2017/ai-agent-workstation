@echo off
REM launch-server.bat — Quick launcher for AI Workstation
REM Double-click this file or run from cmd.exe
REM
REM Usage:
REM   launch-server.bat              Start services + open desktop
REM   launch-server.bat desktop      Open desktop only
REM   launch-server.bat status       Check server status
REM   launch-server.bat stop         Stop services
REM   launch-server.bat tunnel       SSH tunnel for local access

set SERVER=<server-ip>
set USER=agent
set KEY=%USERPROFILE%\.ssh\hetzner_workstation

if "%1"=="desktop" goto :desktop
if "%1"=="status" goto :status
if "%1"=="stop" goto :stop
if "%1"=="tunnel" goto :tunnel

:full
echo.
echo ==== Starting AI Workstation ====
echo.
echo Starting services on %SERVER%...
ssh -o StrictHostKeyChecking=no -i "%KEY%" root@%SERVER% "pkill -f 'uvicorn.*server' 2>/dev/null; cd /opt/workstation/control-plane && nohup python3 api/server.py > /opt/workstation/logs/api.log 2>&1 & echo 'API started on port 9877'"
echo.
echo Launching Remote Desktop...
start mstsc /v:%SERVER%
echo.
echo ==== Ready ====
echo   Desktop: RDP to %SERVER% (agent / <rdp-password>)
echo   API:     http://%SERVER%:9877
echo   Tunnel:  launch-server.bat tunnel
echo.
goto :end

:desktop
echo Launching Remote Desktop to %SERVER%...
start mstsc /v:%SERVER%
goto :end

:status
echo.
echo ==== Server Status ====
ssh -o StrictHostKeyChecking=no -i "%KEY%" root@%SERVER% "uptime; echo; docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null; echo; curl -s -o /dev/null -w 'API: %%{http_code}\n' http://localhost:9877/api/health 2>/dev/null"
goto :end

:stop
echo Stopping services...
ssh -o StrictHostKeyChecking=no -i "%KEY%" root@%SERVER% "pkill -f 'uvicorn.*server' 2>/dev/null; cd /home/agent/ai-workstation && docker compose down 2>/dev/null"
echo Done.
goto :end

:tunnel
echo Starting SSH tunnel (Ctrl+C to stop)...
echo   localhost:4000 = LiteLLM
echo   localhost:3000 = OpenHands
echo   localhost:9877 = Control Plane API
ssh -o StrictHostKeyChecking=no -i "%KEY%" -N -L 4000:localhost:4000 -L 3000:localhost:3000 -L 9877:localhost:9877 root@%SERVER%
goto :end

:end
