# session-list.ps1
# Lists all active sessions on the workstation.
# Usage: .\session-list.ps1 [-KeyPath path\to\key]

param(
    # Workstation IP or Tailscale hostname. Required — pass -Server or edit the default below.
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key"
)

if ($Server -eq "<server-ip>") {
    Write-Host "ERROR: -Server is required. Example:" -ForegroundColor Red
    Write-Host "  .\session-list.ps1 -Server <your-server-ip-or-tailscale-hostname>" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== Active Sessions ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $KeyPath)) {
    Write-Host "SSH key not found: $KeyPath" -ForegroundColor Red
    exit 1
}

ssh -i $KeyPath -o ConnectTimeout=10 "${User}@${Server}" "python3 /opt/workstation/control-plane/cli/platformctl.py session list"
