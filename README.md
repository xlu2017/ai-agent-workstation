# AI Coding Agent Workstation

A production-quality, self-hosted development workstation for AI coding agents. Runs OpenHands with DeepSeek models via LiteLLM Proxy on Hetzner Cloud, with multi-agent worktree isolation, knowledge system, observability, and control-plane-owned UI/context automation.

## Session Platform Intent

The control plane treats repositories, goals, work sessions, app compositions, adapters, runtimes, validation runs, and questions as graph-addressable sessions. Session movement should preserve source identity, record adapter intent, validate policy before mutation, and project only relevant context into execution.

Normative docs:

- [Session platform intent](docs/session-platform-intent.md)
- [Session graph API](docs/api-session-graph.md)
- [Session adapter control-plane behavior](docs/session-adapter-control-plane.md)
- [Deprecated top-level folders](docs/deprecated-top-level-folders.md)

Future work should keep the FastAPI models, API routes, SQL scaffold, UI panels, and `agent-core` contracts aligned. Divergence between those surfaces should be treated as a bug.

## Current Deployment

| Component | Status |
|-----------|--------|
| Hetzner Cloud VM | CCX33-class, 8 vCPU, 32GB RAM |
| LiteLLM Proxy | Running on port 4000 (healthy), monthly spend cap |
| OpenHands | Running on port 3000 / allocated 3010+ |
| Control Plane | Running on port 9877 |
| DeepSeek API | Active (V4-Flash primary) |
| Remote Desktop | xRDP on port 3389 (XFCE 4) |
| Browser Remote Desktop | Apache Guacamole via `/remote-desktop` and `/guacamole/` |
| Node Exporter | Active on port 9100 |
| Chrome | Installed with remote debugging support |
| BorgBackup | Configured, daily 3AM cron |
| Knowledge System | YAML knowledge files loaded |
| Worktree Scripts | Installed at /opt/workstation/scripts/ |

## Quick Start

```bash
# SSH into the server over Tailscale
ssh agent@<tailscale-hostname>

# Check status
cd ~/ai-workstation && docker compose ps

# Access private web UIs via SSH port forward over Tailscale:
ssh -L 9877:localhost:9877 -L 4000:localhost:4000 agent@<tailscale-hostname>
# Then open http://localhost:9877 or http://localhost:4000/ui locally

# RDP for graphical desktop, only when allowed by Tailscale/provider policy:
# Host: <tailscale-hostname>, Port: 3389, User: agent

# Browser remote desktop through Guacamole:
# See docs/operations/remote-desktop.md
```

## Architecture

```text
Hetzner Cloud CCX33 ($74/mo)
├── OpenHands (AI agent runtime, port 3000 / allocated 3010+)
├── LiteLLM Proxy (model gateway, port 4000)
│   └── DeepSeek V4-Flash → Qwen → Claude (fallback chain)
├── Control Plane (API + dashboard, port 9877)
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
├── Apache Guacamole (browser remote desktop via private :8080 / proxy)
├── Control-plane UI/context automation routes (:9877)
└── Security (Tailscale SSH, provider firewall, chrony, SSH key-only fallback)
```

See [docs/architecture.md](docs/architecture.md) for full details.

## Repository Structure

```text
.
├── .agents/                       # Agent skills consumed by coding assistants
├── control-plane/                 # Active FastAPI control plane, web UI, CLI, routes, tests
├── vendor/                        # Vendored runtime dependencies (see vendor/README.md)
├── config/                        # LiteLLM and service configuration
├── scripts/                       # Worktree, backup, workstation, and local-client scripts
├── ops/                           # Active operational stacks such as Guacamole remote desktop
├── knowledge/                     # YAML knowledge files
├── docs/                          # Architecture, operations, API, and deprecation docs
├── rfcs/                          # Forward-looking design proposals
├── bench-apps/                    # Benchmark application evaluations
├── bench-scripts/                 # Benchmark runner scripts
├── bench-tasks/                   # Benchmark task fixtures
├── bench-results/                 # Benchmark output artifacts
├── demo-monorepo/                 # Demo fixture monorepo used by demo scripts
├── docker-compose.yml             # Service orchestration
├── setup.sh                       # Idempotent server setup
└── .env.example                   # API key template
```

### Deprecated top-level folders

The following root folders are retained only as legacy references and must not receive new product behavior:

```text
glue/                  # Deprecated standalone glue layer and legacy session CLI
demo/                  # Deprecated hard-coded legacy demo scripts
browser-extension/     # Deprecated standalone Chrome extension prototype
ui-bridge-service/     # Deprecated standalone source-resolution service
```

Use `control-plane/` for product behavior, session identity, UI/context routing, visual automation, and capability gating. See [Deprecated top-level folders](docs/deprecated-top-level-folders.md) for the governing rules.

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

## Network Access Model

This repository no longer installs or manages `ufw` or `fail2ban`.

Target posture:

- **Public internet:** denied by the provider firewall by default. Allow public TCP/22 only temporarily for break-glass recovery.
- **Tailscale:** primary admin path. Tailscale SSH handles tailnet port 22.
- **OpenSSH fallback:** ordinary OpenSSH is moved to `127.0.0.1:2222` by `scripts/server/configure-tailscale-ssh-only.sh`.
- **Admin services:** Control Plane, LiteLLM, OpenHands, xRDP, metrics, and browser/context automation surfaces are private; access them through Tailscale policy or SSH forwarding.

After Tailscale is authenticated and reachable from an admin device:

```bash
sudo /opt/workstation/scripts/configure-tailscale-ssh-only.sh
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
| Languages | Node.js, Python, zsh |
| Package Mgmt | npm, uv, pipx |
| Containers | Docker Engine, Docker Compose |
| Dev Tools | git, tmux, ripgrep, fd, jq, htop, ncdu |
| Build | build-essential, curl, wget, unzip |
| Browser | Google Chrome / Chromium |
| Backup | BorgBackup |
| Monitoring | prometheus-node-exporter |
| Security | Tailscale, provider firewall, chrony, unattended-upgrades |

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

- **Network:** provider firewall blocks public admin ingress; Tailscale ACLs/grants control tailnet access
- **SSH:** Tailscale SSH for tailnet port 22; OpenSSH key-only fallback on `127.0.0.1:2222`
- **Secrets:** `.env` file (600 permissions, never committed)
- **Docker:** Agent sandboxes isolated from host
- **Updates:** unattended-upgrades for automatic security patches
- **Time:** chrony for NTP synchronization
- **LiteLLM:** Protected by master key, monthly spend cap

## License

Original work in this repository is released under the [MIT License](LICENSE).

Vendored projects under `vendor/` and `control-plane/vendor/` carry their own
upstream licenses — review them before redistributing or modifying vendored
source. Terms declared in `control-plane/vendor/*/manifest.json`:

| Project | License |
|---------|---------|
| n8n | Sustainable Use License / n8n Enterprise License |
| Skyvern | AGPL-3.0 (core; upstream notes managed-cloud exceptions) |
| Activepieces | MIT (Community Edition); commercial license for enterprise features |
| Composio, Stagehand, Browser Use | MIT |
| MCP reference servers | Apache-2.0 / MIT per upstream repository |
| OpenHands SDK (`vendor/openhands-sdk/`) | MIT (upstream OpenHands software-agent-sdk) |

Other vendored ambient-context providers (Playwright, watchfiles, Tree-sitter,
pygls, pyte, OpenTelemetry, python-lsp-server, source-map) remain under their
respective upstream licenses.
