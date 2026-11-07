# Windows Launch Scripts

Scripts for managing the workstation from Windows.

## Prerequisites

1. SSH key at `%USERPROFILE%\.ssh\workstation_key` (or pass `-KeyPath` to scripts)
2. OpenSSH client (built into Windows 10+)

## Scripts

| Script | Purpose |
|--------|---------|
| `launch-dashboard.ps1` | Opens SSH tunnel + dashboard in browser |
| `launch-dashboard.bat` | Same as above, double-click friendly |
| `connect.ps1` | Interactive SSH session |
| `health-check.ps1` | Run `platformctl doctor` |
| `session-list.ps1` | List active sessions |
| `run-demo.ps1` | Run three-session demo |

## Quick Start

```powershell
# Open dashboard (stays open until Ctrl+C)
.\launch-dashboard.ps1

# Check server health
.\health-check.ps1

# List sessions
.\session-list.ps1

# Run the full demo
.\run-demo.ps1
```

## If your key is elsewhere

```powershell
.\launch-dashboard.ps1 -KeyPath C:\Users\you\.ssh\my_key
```

## Ports forwarded by launch-dashboard

| Local | Remote | Service |
|-------|--------|---------|
| 9877 | 9877 | Control Plane Dashboard |
| 9876 | 9876 | UI Bridge (context events) |
