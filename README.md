# AI Coding Agent Workstation

A production-quality, self-hosted development workstation for AI coding agents. Runs OpenHands with DeepSeek models via LiteLLM Proxy on Hetzner Cloud, with multi-agent worktree isolation, knowledge system, observability, and UI-to-code bridging.

## Current Deployment

| Component | Status |
|-----------|--------|
| Server | `ubuntu-32gb-fsn1-1` — CCX33, 8 vCPU, 32GB RAM, Falkenstein |
| IP | `167.233.31.65` |
| LiteLLM Proxy | Running on port 4000 (healthy), budget: $150/mo cap |
| OpenHands | Running on port 3000 |
| DeepSeek API | Active (V4-Flash primary) |
| Remote Desktop | xRDP on port 3389 (XFCE 4) |
| Node Exporter | Active on port 9100 |
| Chrome | v149, installed with remote debugging support |
| BorgBackup | Configured, daily 3AM cron |
| Knowledge System | 2 knowledge files loaded |
| Worktree Scripts | Installed at /opt/workstation/scripts/ |

## Quick Start

```bash
# SSH into the server
ssh -i ~/.ssh/hetzner_workstation agent@167.233.31.65

# Check status
cd ~/ai-workstation && docker compose ps

# Access web UIs via SSH port forward:
ssh -L 3000:localhost:3000 -L 4000:localhost:4000 -i ~/.ssh/hetzner_workstation agent@167.233.31.65
# Then open http://localhost:3000 in your local browser

# RDP for graphical desktop:
# Host: 167.233.31.65, Port: 3389, User: agent
```

## Architecture

```
Hetzner Cloud CCX33 ($74/mo)
├── OpenHands (AI agent runtime, port 3000)
├── LiteLLM Proxy (model gateway, port 4000)
│   └── DeepSeek V4-Flash → Qwen → Claude (fallback chain)
├── Docker Engine (agent sandboxes)
├── /opt/workstation/
│   ├── repos/          (git bare repos + worktrees)
│   ├── knowledge/      (YAML knowledge files)
│   ├── scripts/        (worktree, backup, knowledge-loader)
│   ├── logs/           (application logs)
│   └── backups/        (BorgBackup repository)
├── Observability (prometheus-node-exporter :9100)
├── Chrome (remote debugging :9222)
├── xRDP + XFCE4 (remote desktop :3389)
├── UI-Bridge Service (source map resolution :9876)
└── Security (ufw, fail2ban, chrony, SSH key-only)
```

See [docs/architecture.md](docs/architecture.md) for full details.

## Repository Structure

```
.
├── docker-compose.yml              # Service orchestration
├── setup.sh                        # Idempotent server setup
├── .env.example                    # API key template
├── config/
│   └── litellm_config.yaml         # Model routing + budget limits
├── scripts/
│   ├── create-worktree.sh          # Create isolated agent workspace
│   ├── destroy-worktree.sh         # Clean up worktree + resources
│   ├── list-worktrees.sh           # Show active worktrees
│   ├── backup-now.sh               # Manual BorgBackup
│   └── knowledge-loader.py         # Context-aware knowledge activation
├── knowledge/
│   ├── example-react.yaml          # React patterns knowledge
│   └── example-python.yaml         # Python patterns knowledge
├── browser-extension/              # UI-to-Code bridge (Phase 1)
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   └── popup.html
├── ui-bridge-service/              # Source map resolution server
│   ├── server.py
│   └── ARCHITECTURE.md
├── docs/
│   ├── architecture.md             # System architecture
│   ├── provider-comparison.md      # Infra & API comparison
│   ├── cost-model.md               # Budget projections
│   ├── operations.md               # Day-to-day operations
│   ├── troubleshooting.md          # Common issues & fixes
│   ├── upgrade.md                  # Upgrade procedures
│   └── backup.md                   # Backup & restore
└── rfcs/
    ├── RFC-001-multi-agent-scheduler.md
    ├── RFC-002-source-aware-ui-selection.md
    ├── RFC-003-react-native-bridge.md
    ├── RFC-004-flutter-bridge.md
    ├── RFC-005-android-emulator-integration.md
    ├── RFC-006-burst-gpu-workers.md
    ├── RFC-007-persistent-agent-memory.md
    └── RFC-008-vm-snapshot-management.md
```

## Multi-Agent Worktrees

Each agent session gets isolated resources:

```bash
# Clone repo as bare (once)
git clone --bare https://github.com/user/repo.git /opt/workstation/repos/repo.git

# Create worktree for agent
/opt/workstation/scripts/create-worktree.sh repo feature/new-api main
# → Creates: worktree, tmux session, browser profile, port allocation

# List active
/opt/workstation/scripts/list-worktrees.sh

# Destroy when done
/opt/workstation/scripts/destroy-worktree.sh repo-feature-new-api
```

## Knowledge System

YAML-based knowledge files activate based on task context:

```bash
python3 /opt/workstation/scripts/knowledge-loader.py \
  --task "Create a React component with useState" \
  --packages react typescript
# → Activates: react-patterns (score 8.5)
```

## Installed Tools

| Category | Tools |
|----------|-------|
| Languages | Node.js 22, Python 3.14, zsh |
| Package Mgmt | npm, uv, pipx |
| Containers | Docker Engine, Docker Compose |
| Dev Tools | git, tmux, ripgrep, fd, jq, htop, ncdu |
| Build | build-essential, curl, wget, unzip |
| Browser | Google Chrome 149 |
| Backup | BorgBackup 1.4.4 |
| Monitoring | prometheus-node-exporter |
| Security | ufw, fail2ban, chrony, unattended-upgrades |

## Cost Summary

| Scenario | Monthly |
|----------|---------|
| Paused (snapshot only) | $0.36 |
| Light (5 sessions/day) | ~$92 |
| Moderate (20 sessions/day) | ~$107 |
| Heavy (50 sessions/day) | ~$143 |

All under $200/month. See [docs/cost-model.md](docs/cost-model.md).

## Remote Desktop Recommendation

**Evaluated:**
- **Option A: NoMachine** — Commercial, efficient NX protocol, good for CPU-only servers
- **Option B: Sunshine + Moonlight** — Open-source, low-latency game streaming protocol

**Recommendation: xRDP (current) + NoMachine (future upgrade)**

For a CPU-only cloud server, xRDP provides reliable baseline access. NoMachine offers better performance (NX protocol is more efficient than RDP for interactive use). Sunshine/Moonlight excels on GPU-equipped servers but requires hardware encoding (NVENC/VAAPI) for optimal performance.

For future Android emulator use (RFC-005), upgrade to Sunshine when GPU hardware is available.

## Security

- **Network:** ufw restricts to SSH (22) + RDP (3389) only
- **SSH:** Key-only authentication (Ed25519), fail2ban enabled
- **Secrets:** `.env` file (600 permissions, never committed)
- **Docker:** Agent sandboxes isolated from host
- **Updates:** unattended-upgrades for automatic security patches
- **Time:** chrony for NTP synchronization
- **LiteLLM:** Protected by master key, $150/mo budget cap
