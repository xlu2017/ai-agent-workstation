# session-list.ps1
# Lists all active sessions on the workstation.
# Usage: .\session-list.ps1 [-KeyPath path\to\key]

param(
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key"
)

Write-Host "=== Active Sessions ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $KeyPath)) {
    Write-Host "SSH key not found: $KeyPath" -ForegroundColor Red
    exit 1
}

ssh -i $KeyPath -o ConnectTimeout=10 "${User}@${Server}" "python3 /opt/workstation/control-plane/cli/platformctl.py session list"
