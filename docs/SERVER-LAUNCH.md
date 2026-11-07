# Server Launch Guide

## Overview

The AI Workstation runs on a Hetzner CCX33 server (<server-ip>) with:
- **xRDP** — Remote desktop (XFCE4) on port 3389
- **Control Plane API** — FastAPI on port 9877
- **LiteLLM** — Model proxy on port 4000 (requires API keys)
- **OpenHands** — AI coding agent on port 3000 (requires API keys)
- **Benchmark Suite** — 10 seeded bug tasks for evaluation

---

## Quick Start (Windows)

### Option A: Double-click launcher
```
scripts\windows\launch-server.bat
```
This starts services and opens the remote desktop.

### Option B: PowerShell (more control)
```powershell
# Full launch (services + desktop)
.\scripts\windows\launch-server.ps1

# Desktop only
.\scripts\windows\launch-server.ps1 -Desktop

# Check status
.\scripts\windows\launch-server.ps1 -Status

# SSH tunnel (access services at localhost)
.\scripts\windows\launch-server.ps1 -Tunnel

# Stop everything
.\scripts\windows\launch-server.ps1 -Stop
```

### Prerequisites (Windows)
1. SSH key at `%USERPROFILE%\.ssh\workstation_key`
2. OpenSSH client installed (built into Windows 10+)
3. Remote Desktop Connection (built into Windows)

---

## Server Auto-Start (Linux)

### Install systemd service (one-time)
```bash
sudo bash /opt/workstation/scripts/install-service.sh
```

After this, all services start automatically on every server boot.

### What starts on boot
1. Docker daemon
2. Docker Compose (LiteLLM + OpenHands, if .env configured)
3. Control Plane API (port 9877)
4. xRDP (port 3389)
5. Firewall rules verified

### Management
```bash
# Check status
sudo systemctl status workstation

# Restart all services
sudo systemctl restart workstation

# Stop all services
sudo systemctl stop workstation

# View startup logs
journalctl -u workstation -f

# View API logs
tail -f /opt/workstation/logs/api.log
```

### Manual startup (without systemd)
```bash
sudo /opt/workstation/scripts/workstation-startup.sh
```

---

## Server Configuration

### Configure API keys (required for LiteLLM + OpenHands)
```bash
sudo nano /home/agent/ai-workstation/.env
```

Required keys:
```
DEEPSEEK_API_KEY=sk-...          # Primary (required)
LITELLM_MASTER_KEY=<generate>    # openssl rand -hex 32
```

Optional fallbacks:
```
DASHSCOPE_API_KEY=sk-...         # Qwen fallback
ANTHROPIC_API_KEY=sk-...         # Claude fallback
OPENAI_API_KEY=sk-...            # GPT fallback
GEMINI_API_KEY=...               # Gemini fallback
```

After editing .env:
```bash
sudo systemctl restart workstation
```

---

## Ports

| Port | Service | Access |
|------|---------|--------|
| 22 | SSH | Public |
| 3389 | xRDP (desktop) | Public |
| 9877 | Control Plane API | Public |
| 4000 | LiteLLM | Internal (use tunnel) |
| 3000 | OpenHands | Internal (use tunnel) |

### SSH Tunnel for local access
```bash
ssh -i ~/.ssh/workstation_key -N \
    -L 4000:localhost:4000 \
    -L 3000:localhost:3000 \
    -L 9877:localhost:9877 \
    root@<server-ip>
```

Then access at `http://localhost:4000`, etc.

---

## Credentials

| Service | Username | Password |
|---------|----------|----------|
| xRDP Desktop | agent | <rdp-password> |
| SSH | root | (key-based only) |
| Control Plane API | — | No auth (internal) |

---

## Directory Structure

```
/opt/workstation/
├── bench-apps/          # Benchmark repos (cypress-realworld-app, etc.)
├── bench-tasks/         # Seeded bug tasks (10 for cypress-realworld-app)
├── bench-scripts/       # run-benchmark.py, summarize-results.py
├── bench-results/       # Benchmark run results
├── control-plane/       # API, CLI, dashboard source
│   ├── api/server.py
│   ├── cli/platformctl.py
│   └── web/src/App.tsx
├── sessions/            # Active agent sessions
├── repos/               # Worktree repos
├── knowledge/           # Knowledge base
├── logs/                # Service logs
└── scripts/             # Startup/shutdown scripts

/home/agent/ai-workstation/
├── docker-compose.yml   # LiteLLM + OpenHands
└── .env                 # API keys (not committed)
```

---

## Troubleshooting

### RDP won't connect
```bash
# Check xRDP
ssh root@<server-ip> "systemctl status xrdp"

# Check firewall
ssh root@<server-ip> "ufw status | grep 3389"

# Restart xRDP
ssh root@<server-ip> "systemctl restart xrdp"
```

### API not responding
```bash
# Check if running
ssh root@<server-ip> "curl -s http://localhost:9877/api/health"

# Restart
ssh root@<server-ip> "pkill -f 'uvicorn.*server'; cd /opt/workstation/control-plane && nohup python3 api/server.py > /opt/workstation/logs/api.log 2>&1 &"
```

### Docker services not starting
```bash
# Check .env
ssh root@<server-ip> "grep DEEPSEEK /home/agent/ai-workstation/.env"

# Check docker
ssh root@<server-ip> "docker compose -f /home/agent/ai-workstation/docker-compose.yml logs --tail 20"
```

### Benchmark tasks
```bash
# List tasks
ssh root@<server-ip> "python3 /opt/workstation/bench-scripts/run-benchmark.py list"

# Run one task
ssh root@<server-ip> "python3 /opt/workstation/bench-scripts/run-benchmark.py run --repo cypress-realworld-app --task disabled-submit-button"
```
