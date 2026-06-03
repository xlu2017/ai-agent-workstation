# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hetzner Cloud CCX33                           │
│              8 vCPU (dedicated) · 32 GB · 240 GB                │
│                                                                 │
│  ┌───────────┐  ┌────────────┐  ┌─────────────────────────┐   │
│  │ OpenHands │  │  LiteLLM   │  │    Observability         │   │
│  │  :3000    │  │  Proxy     │  │  node-exporter :9100     │   │
│  │           │  │  :4000     │  │  (future: Grafana :3001) │   │
│  └─────┬─────┘  └─────┬──────┘  └─────────────────────────┘   │
│        │               │                                        │
│        │  ┌────────────┴──────────────────┐                    │
│        │  │        Model APIs              │                    │
│        │  │  DeepSeek ─→ DashScope ─→ ...  │                    │
│        │  └───────────────────────────────┘                    │
│        │                                                        │
│  ┌─────┴───────────────────────────────────────────────────┐   │
│  │                Docker Engine                             │   │
│  │  Persistent volumes · Restart policies · Networks        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              /opt/workstation                            │   │
│  │  repos/ · knowledge/ · scripts/ · logs/ · backups/      │   │
│  │  Git worktrees · tmux sessions · Browser profiles       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌────────────┐  ┌───────────┐  ┌────────────────────────┐    │
│  │   Chrome   │  │   xRDP    │  │    UI-Bridge Service    │    │
│  │  + DevTools│  │   :3389   │  │      :9876              │    │
│  └────────────┘  └───────────┘  └────────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Ubuntu 24.04 LTS · fail2ban · ufw · chrony             │   │
│  │  unattended-upgrades · SSH key-only                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Roles

| Component | Purpose | Port | Container |
|-----------|---------|------|-----------|
| OpenHands | AI agent runtime | 3000 | Yes |
| LiteLLM Proxy | Model routing, budget, logging | 4000 | Yes |
| Chrome | Browser for agents, DevTools | 9222 (debug) | No |
| xRDP | Remote desktop access | 3389 | No |
| UI-Bridge | Source map resolution | 9876 | No |
| Node Exporter | System metrics | 9100 | No |
| BorgBackup | Encrypted backups | — | No |

## Directory Layout

```
/opt/workstation/
├── repos/              # Git bare repos and worktrees
├── knowledge/          # YAML knowledge files
├── scripts/            # Helper scripts (worktree, backup, etc.)
├── logs/               # Application and worktree logs
├── backups/            # BorgBackup repository
└── profiles/           # Per-worktree Chrome profiles

/home/agent/ai-workstation/
├── docker-compose.yml  # Service orchestration
├── config/             # LiteLLM, Caddy configs
├── .env                # API keys (not committed)
└── ...                 # Documentation
```

## Multi-Agent Design

Each agent session gets:
- **Git worktree** — Isolated branch from bare repository
- **tmux session** — Persistent terminal
- **Browser profile** — Isolated Chrome data dir
- **Port range** — 10 ports per worktree (e.g., 5000-5009, 5010-5019)

```
Agent 1:  worktree/feature-auth  →  tmux: agent-feature-auth  →  ports 5000-5009
Agent 2:  worktree/fix-api       →  tmux: agent-fix-api       →  ports 5010-5019
Agent 3:  worktree/new-ui        →  tmux: agent-new-ui        →  ports 5020-5029
```

## Network Security

```
Internet → ufw (allow 22, 3389) → fail2ban → services
                                              ├── :3000 OpenHands (localhost)
                                              ├── :4000 LiteLLM (localhost)
                                              ├── :9100 Node Exporter (localhost)
                                              └── :9876 UI-Bridge (localhost)
```

Only SSH (22) and RDP (3389) are exposed publicly.
Services are accessed via SSH port forwarding or Tailscale.

## Future: Dedicated Hardware Migration

The entire stack is portable:
1. Snapshot current cloud server
2. Provision Hetzner AX42-U dedicated ($59/mo)
3. Restore from BorgBackup or re-run setup.sh
4. No config changes needed — all paths are absolute and consistent

## Future: GPU Burst Workers

```
Workstation (Hetzner) ←──API──→ RunPod GPU Worker (on-demand)
     │                              │
     └── LiteLLM routes to ──────→ local vLLM instance
         when budget allows          (DeepSeek-V3 self-hosted)
```

See RFC-006 for details.
