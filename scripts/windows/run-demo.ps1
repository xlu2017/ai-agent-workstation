# run-demo.ps1
# Runs the three-session demo on the remote server.
# Usage: .\run-demo.ps1 [-KeyPath path\to\key]

param(
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key"
)

Write-Host "=== Three-Session Demo ===" -ForegroundColor Cyan
Write-Host "Server: $Server" -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path $KeyPath)) {
    Write-Host "SSH key not found: $KeyPath" -ForegroundColor Red
    exit 1
}

ssh -i $KeyPath -o ConnectTimeout=10 -o ServerAliveInterval=30 "${User}@${Server}" "bash /opt/workstation/demo/three-session-demo.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Demo completed successfully!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Demo failed with exit code $LASTEXITCODE" -ForegroundColor Red
}
