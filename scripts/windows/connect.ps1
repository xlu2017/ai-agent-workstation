# connect.ps1
# Opens an interactive SSH session to the workstation.
# Usage: .\connect.ps1 [-KeyPath path\to\key]

param(
    # Workstation IP or Tailscale hostname. Required — pass -Server or edit the default below.
    [string]$Server = "<server-ip>",
    [string]$User = "agent",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\workstation_key"
)

if ($Server -eq "<server-ip>") {
    Write-Host "ERROR: -Server is required. Example:" -ForegroundColor Red
    Write-Host "  .\connect.ps1 -Server <your-server-ip-or-tailscale-hostname>" -ForegroundColor Yellow
    exit 1
}

Write-Host "Connecting to workstation at $Server..." -ForegroundColor Cyan

if (-not (Test-Path $KeyPath)) {
    Write-Host "SSH key not found: $KeyPath" -ForegroundColor Red
    Write-Host "Place your key at: $KeyPath" -ForegroundColor Yellow
    Write-Host "Or run: .\connect.ps1 -KeyPath C:\path\to\your\key" -ForegroundColor Yellow
    exit 1
}

ssh -i $KeyPath -o ServerAliveInterval=30 "${User}@${Server}"
