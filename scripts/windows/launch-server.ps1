# launch-server.ps1 — Launch the AI Workstation server from Windows
#
# Usage:
#   .\launch-server.ps1              # Full launch (services + desktop)
#   .\launch-server.ps1 -Desktop     # Desktop only (RDP)
#   .\launch-server.ps1 -Services    # Start services only (no desktop)
#   .\launch-server.ps1 -Status      # Check server status
#   .\launch-server.ps1 -Stop        # Stop all services
#
# Prerequisites:
#   - SSH key at ~\.ssh\workstation_key
#   - Server at <server-ip> with setup.sh already run

param(
    [switch]$Desktop,
    [switch]$Services,
    [switch]$Status,
    [switch]$Stop,
    [switch]$Tunnel,
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key"
)

$ErrorActionPreference = "Continue"

# --- Configuration ---
$SSH_OPTS = @("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-i", $KeyPath)
$RDP_PORT = 3389
$API_PORT = 9877
$LITELLM_PORT = 4000
$OPENHANDS_PORT = 3000

function Write-Header($msg) {
    Write-Host ""
    Write-Host "==== $msg ====" -ForegroundColor Cyan
    Write-Host ""
}

function Test-SSHConnection {
    Write-Host "Testing SSH connection to $Server..." -ForegroundColor Yellow
    $result = & ssh @SSH_OPTS "${User}@${Server}" "echo ok" 2>&1
    if ($result -match "ok") {
        Write-Host "  SSH connection OK" -ForegroundColor Green
        return $true
    }
    # Try root if agent fails
    $result = & ssh @SSH_OPTS "root@${Server}" "echo ok" 2>&1
    if ($result -match "ok") {
        Write-Host "  SSH connection OK (root)" -ForegroundColor Green
        return $true
    }
    Write-Host "  SSH connection FAILED" -ForegroundColor Red
    Write-Host "  Ensure key exists at: $KeyPath" -ForegroundColor Red
    return $false
}

function Get-ServerStatus {
    Write-Header "Server Status"
    
    if (-not (Test-SSHConnection)) { return }

    $status = & ssh @SSH_OPTS "root@${Server}" @"
echo '--- System ---'
uptime
echo ''
echo '--- Docker ---'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo 'Docker not running'
echo ''
echo '--- Services ---'
systemctl is-active xrdp 2>/dev/null | xargs -I{} echo "xRDP: {}"
curl -s -o /dev/null -w 'Control Plane API: %{http_code}\n' http://localhost:9877/api/health 2>/dev/null || echo 'Control Plane API: not running'
curl -s -o /dev/null -w 'LiteLLM: %{http_code}\n' http://localhost:4000/health 2>/dev/null || echo 'LiteLLM: not running'
echo ''
echo '--- Disk ---'
df -h / | tail -1 | awk '{print "Used: " $3 " / " $2 " (" $5 ")"}'
echo ''
echo '--- Benchmark ---'
python3 /opt/workstation/bench-scripts/run-benchmark.py list 2>/dev/null | tail -1
"@
    Write-Host $status
}

function Start-Services {
    Write-Header "Starting Services"
    
    if (-not (Test-SSHConnection)) { return }

    Write-Host "Starting control plane API..." -ForegroundColor Yellow
    & ssh @SSH_OPTS "root@${Server}" @"
# Kill existing if running
pkill -f 'uvicorn.*server' 2>/dev/null || true
sleep 1

# Start control plane API
cd /opt/workstation/control-plane
nohup python3 api/server.py > /opt/workstation/logs/api.log 2>&1 &
echo "  Control Plane API started (port $API_PORT)"

# Start Docker services if .env exists
if [ -f /home/agent/ai-workstation/.env ] && grep -q 'DEEPSEEK_API_KEY=sk-' /home/agent/ai-workstation/.env 2>/dev/null; then
    cd /home/agent/ai-workstation
    docker compose up -d 2>&1 | tail -3
    echo "  Docker services started"
else
    echo "  Docker services skipped (no API keys in .env)"
    echo "  To configure: ssh root@$Server 'nano /home/agent/ai-workstation/.env'"
fi
"@

    Write-Host ""
    Write-Host "Services started." -ForegroundColor Green
    Write-Host "  API: http://${Server}:${API_PORT}" -ForegroundColor Gray
    Write-Host "  LiteLLM: http://${Server}:${LITELLM_PORT} (if configured)" -ForegroundColor Gray
    Write-Host "  OpenHands: http://${Server}:${OPENHANDS_PORT} (if configured)" -ForegroundColor Gray
}

function Start-Desktop {
    Write-Header "Launching Remote Desktop"
    
    Write-Host "Connecting to ${Server}:${RDP_PORT}..." -ForegroundColor Yellow
    Start-Process "mstsc.exe" -ArgumentList "/v:${Server}:${RDP_PORT}"
    Write-Host "  RDP client launched." -ForegroundColor Green
    Write-Host "  Login: agent / <rdp-password>" -ForegroundColor Gray
}

function Start-Tunnel {
    Write-Header "Starting SSH Tunnel"
    
    Write-Host "Forwarding local ports to server..." -ForegroundColor Yellow
    Write-Host "  localhost:4000 -> LiteLLM" -ForegroundColor Gray
    Write-Host "  localhost:3000 -> OpenHands" -ForegroundColor Gray
    Write-Host "  localhost:9877 -> Control Plane API" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Press Ctrl+C to stop the tunnel." -ForegroundColor Yellow
    
    & ssh @SSH_OPTS -N `
        -L "4000:localhost:4000" `
        -L "3000:localhost:3000" `
        -L "9877:localhost:9877" `
        "root@${Server}"
}

function Stop-Services {
    Write-Header "Stopping Services"
    
    if (-not (Test-SSHConnection)) { return }

    & ssh @SSH_OPTS "root@${Server}" @"
pkill -f 'uvicorn.*server' 2>/dev/null && echo "  Control Plane API stopped" || echo "  Control Plane API was not running"
cd /home/agent/ai-workstation 2>/dev/null && docker compose down 2>&1 | tail -2 || echo "  Docker services were not running"
"@
    Write-Host ""
    Write-Host "Services stopped." -ForegroundColor Green
}

# --- Main ---

if ($Status) {
    Get-ServerStatus
}
elseif ($Stop) {
    Stop-Services
}
elseif ($Tunnel) {
    Start-Tunnel
}
elseif ($Desktop -and -not $Services) {
    Start-Desktop
}
elseif ($Services -and -not $Desktop) {
    Start-Services
}
else {
    # Default: start everything
    Start-Services
    Start-Desktop
    Write-Host ""
    Write-Header "Ready"
    Write-Host "Server is running. Use these commands:" -ForegroundColor White
    Write-Host "  .\launch-server.ps1 -Status    # Check status" -ForegroundColor Gray
    Write-Host "  .\launch-server.ps1 -Desktop   # Reopen desktop" -ForegroundColor Gray
    Write-Host "  .\launch-server.ps1 -Tunnel    # SSH tunnel for local access" -ForegroundColor Gray
    Write-Host "  .\launch-server.ps1 -Stop      # Stop services" -ForegroundColor Gray
}
