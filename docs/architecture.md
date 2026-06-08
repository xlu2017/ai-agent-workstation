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
│  └────────────┘  └─────┬─────┘  └────────────────────────┘    │
│                        │                                        │
│  ┌─────────────────────┴───────────────────────────────────┐   │
│  │  Apache Guacamole webapp :8080 -> guacd -> xRDP          │   │
│  │  Browser route: /remote-desktop and /guacamole/ proxy    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Ubuntu 24.04 LTS · Tailscale · chrony                  │   │
│  │  unattended-upgrades · SSH key-only fallback            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Roles

| Component | Purpose | Port | Container |
|-----------|---------|------|-----------|
| OpenHands | AI agent runtime | 3000 / allocated 3010+ | Yes |
| LiteLLM Proxy | Model routing, budget, logging | 4000 | Yes |
| Control Plane | API + dashboard | 9877 | No |
| Chrome | Browser for agents, DevTools | 9222 (debug) | No |
| xRDP | Remote desktop access | 3389 | No |
| Guacamole | Browser remote desktop gateway | 8080 / `/guacamole/` | Yes |
| guacd | Native remote desktop proxy daemon | 4822 internal | Yes |
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

The workstation does not manage `ufw` or `fail2ban`. Ingress control is split between the provider firewall and Tailscale:

```
Public Internet → Provider firewall → no public admin ingress by default

Tailnet admin device → Tailscale ACLs/grants → workstation tailnet IP
                                                ├── :22   Tailscale SSH
                                                ├── :3389 xRDP, if enabled by policy
                                                ├── :8080 Guacamole, if enabled by policy
                                                ├── :9877 Control Plane, if enabled by policy
                                                ├── :4000 LiteLLM, if enabled by policy
                                                └── :3000/3010+ OpenHands, if enabled by policy

Local-only / SSH-forwarded access               ├── :4000 LiteLLM
                                                ├── :8080 Guacamole webapp
                                                ├── :9100 Node Exporter
                                                └── :9876 UI-Bridge
```

Target posture:

1. Block ordinary public SSH on TCP/22 at the provider firewall.
2. Enable Tailscale SSH for tailnet access to port 22.
3. Move ordinary OpenSSH to `127.0.0.1:2222` as a local console fallback using `scripts/server/configure-tailscale-ssh-only.sh`.
4. Expose xRDP, Control Plane, LiteLLM, and OpenHands only through Tailscale ACLs/grants or SSH port forwarding.
5. Keep a provider-console or temporary provider-firewall break-glass path for recovery.

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
