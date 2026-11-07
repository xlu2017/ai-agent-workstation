# launch-dashboard.ps1
# Opens SSH tunnel to the workstation and launches the dashboard in your browser.
# Usage: .\launch-dashboard.ps1 [-KeyPath path\to\key]

param(
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key",
    [int]$DashboardPort = 9877,
    [int]$BridgePort = 9876
)

Write-Host "=== Workstation Dashboard Launcher ===" -ForegroundColor Cyan
Write-Host ""

# Check SSH key exists
if (-not (Test-Path $KeyPath)) {
    Write-Host "SSH key not found at: $KeyPath" -ForegroundColor Red
    Write-Host "Copy your key to $KeyPath or pass -KeyPath" -ForegroundColor Yellow
    exit 1
}

# Kill existing tunnels
$existing = Get-Process ssh -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*$Server*"
}
if ($existing) {
    Write-Host "Stopping existing SSH tunnels..." -ForegroundColor Yellow
    $existing | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# Start SSH tunnel (dashboard + bridge)
Write-Host "Starting SSH tunnel: localhost:$DashboardPort -> server:$DashboardPort" -ForegroundColor Green
Write-Host "Starting SSH tunnel: localhost:$BridgePort -> server:$BridgePort" -ForegroundColor Green

$sshArgs = @(
    "-i", $KeyPath,
    "-N",
    "-L", "${DashboardPort}:localhost:${DashboardPort}",
    "-L", "${BridgePort}:localhost:${BridgePort}",
    "-o", "ServerAliveInterval=30",
    "-o", "StrictHostKeyChecking=no",
    "${User}@${Server}"
)

$tunnel = Start-Process ssh -ArgumentList $sshArgs -PassThru -WindowStyle Hidden
Write-Host "Tunnel PID: $($tunnel.Id)" -ForegroundColor Gray

Start-Sleep -Seconds 2

# Verify tunnel
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$DashboardPort/api/health" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "Dashboard is reachable!" -ForegroundColor Green
} catch {
    Write-Host "Warning: Dashboard not reachable yet. It may take a moment." -ForegroundColor Yellow
}

# Open browser
Write-Host ""
Write-Host "Opening dashboard in browser..." -ForegroundColor Cyan
Start-Process "http://localhost:$DashboardPort"

Write-Host ""
Write-Host "Dashboard: http://localhost:$DashboardPort" -ForegroundColor White
Write-Host "Press Ctrl+C to close tunnel." -ForegroundColor Gray
Write-Host ""

# Keep running until user cancels
try {
    while ($tunnel.HasExited -eq $false) {
        Start-Sleep -Seconds 5
    }
} finally {
    if (-not $tunnel.HasExited) {
        Stop-Process $tunnel.Id -Force
    }
    Write-Host "Tunnel closed." -ForegroundColor Yellow
}
