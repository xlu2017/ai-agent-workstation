# AI Coding Agent Workstation

A production-quality, self-hosted development workstation for AI coding agents. Runs OpenHands with DeepSeek models via LiteLLM Proxy on a Hetzner Cloud server.

## Current Deployment

| Component | Status |
|-----------|--------|
| Server | `ubuntu-32gb-fsn1-1` — CCX33, 8 vCPU, 32GB RAM, Falkenstein |
| IP | `167.233.31.65` |
| LiteLLM Proxy | Running on port 4000 (healthy) |
| OpenHands | Running on port 3000 |
| DeepSeek API | Active, topped up |
| Remote Desktop | xRDP on port 3389 (XFCE 4) |
| Tailscale | Installed, needs `sudo tailscale up` |

## Quick Start

```bash
# SSH into the server
ssh -i ~/.ssh/hetzner_workstation agent@167.233.31.65

# Services are already running. Check status:
cd ~/ai-workstation && docker compose ps

# Access OpenHands (via SSH port forward):
ssh -L 3000:localhost:3000 -L 4000:localhost:4000 -i ~/.ssh/hetzner_workstation agent@167.233.31.65
# Then open http://localhost:3000 in your local browser

# Or use RDP for graphical desktop:
# Host: 167.233.31.65, Port: 3389, User: agent
```

## Architecture

```
Hetzner Cloud CCX33 ($74/mo)
├── OpenHands (AI agent runtime, port 3000)
├── LiteLLM Proxy (model gateway, port 4000)
│   └── DeepSeek V4-Flash (primary) → Qwen (fallback) → Claude (emergency)
├── Docker (agent sandboxes)
├── xRDP + XFCE4 (remote desktop, port 3389)
├── Tailscale (secure mesh VPN)
├── tmux (session management)
└── Git worktrees (parallel agent workspaces)
```

**Model routing:** DeepSeek V4-Flash (primary, $0.14/M tokens) → Qwen-turbo (fallback) → Claude Haiku (emergency)

**Total cost:** $80–95/month for moderate usage (well under $200 budget)

## File Structure

```
.
├── setup.sh                    # Idempotent server setup (run as root)
├── docker-compose.yml          # Service definitions
├── .env.example                # Template for secrets
├── config/
│   ├── litellm_config.yaml     # Model routing configuration
│   └── Caddyfile               # Optional HTTPS reverse proxy
├── DEPLOYMENT-LOG.md           # Complete deployment record
├── remote-desktop-guide.md     # RDP/SSH/Tailscale access guide
├── operations.md               # Day-to-day operations guide
├── backup.md                   # Backup, restore, pause/resume
├── provider-comparison.md      # Infrastructure & API comparison
├── cost-model.md               # Budget projections
├── recommended-architecture.md # Architecture decisions
├── provisioning-plan.md        # Step-by-step provisioning
└── risks-and-mitigations.md    # Risk analysis
```

## Access Methods

| Method | Use Case | Command |
|--------|----------|---------|
| SSH | Terminal access | `ssh -i ~/.ssh/hetzner_workstation agent@167.233.31.65` |
| SSH + Port Forward | Web UIs locally | `ssh -L 3000:localhost:3000 -L 4000:localhost:4000 ...` |
| RDP | Full graphical desktop | Any RDP client → `167.233.31.65:3389` |
| VS Code Remote | IDE with extensions | Remote-SSH extension → `agent@167.233.31.65` |
| Tailscale | Secure private access | `sudo tailscale up` on server first |

See [remote-desktop-guide.md](remote-desktop-guide.md) for detailed instructions.

## Key Operations

| Task | Command |
|------|---------|
| Start services | `cd ~/ai-workstation && docker compose up -d` |
| Stop services | `cd ~/ai-workstation && docker compose down` |
| View logs | `docker compose logs -f` |
| Check health | `curl -s http://localhost:4000/health/liveliness` |
| Test API | `curl -H "Authorization: Bearer $KEY" http://localhost:4000/v1/chat/completions -d '...'` |
| Start tmux sessions | `~/ai-workstation/scripts/start-sessions.sh` |
| Pause workstation | Snapshot → Delete server (see [backup.md](backup.md)) |
| Resume workstation | Create server from snapshot (30 seconds) |

See [operations.md](operations.md) for comprehensive operations guide.

## Pause/Resume (Cost Saving)

When not in use:

1. **Snapshot the server** via Hetzner Console
2. **Delete the server** (stops billing at $74/mo)
3. **Snapshot storage:** ~$0.36/mo for a 30GB image

To resume: Create new server from snapshot (30 seconds, no setup fee).

See [backup.md](backup.md) for detailed procedures.

## Migration to Dedicated

When ready for always-on use, migrate to Hetzner Dedicated AX42-U ($59/mo):

1. Create snapshot of cloud server
2. Order AX42-U (1–5 day delivery)
3. rsync from cloud → dedicated
4. Update Tailscale routing
5. Delete cloud server

All software is infrastructure-agnostic — `setup.sh` works identically on dedicated hardware.

## Security

- **Network:** Tailscale-only access planned (close port 3389 after Tailscale setup)
- **SSH:** Key-only authentication (Ed25519), fail2ban enabled
- **Secrets:** `.env` file (600 permissions, never committed)
- **Docker:** Agent sandboxes isolated from host
- **Updates:** Automatic security patches via unattended-upgrades
- **LiteLLM:** Protected by master key (required for all API calls)

## Requirements

- **Server:** 8+ vCPUs, 32+ GB RAM, Ubuntu 24.04 LTS
- **API keys:** DeepSeek (required), DashScope/Anthropic/OpenAI (optional)
- **Tailscale account:** Free at https://tailscale.com
- **SSH key:** Ed25519 key at `~/.ssh/hetzner_workstation`

## License

Private repository. Not for redistribution.
