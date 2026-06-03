# AI Coding Agent Workstation

A production-quality, self-hosted development workstation for AI coding agents. Runs OpenHands with DeepSeek models via LiteLLM Proxy on a Hetzner Cloud server.

## Quick Start

```bash
# 1. Provision a Hetzner Cloud CCX33 (Ubuntu 24.04)
# 2. SSH in and run:
sudo bash setup.sh

# 3. Configure API keys:
cd /home/agent/ai-workstation
cp .env.example .env
nano .env  # Add your DeepSeek API key at minimum

# 4. Start services:
./scripts/start-services.sh

# 5. Access OpenHands:
#    http://<tailscale-hostname>:3000
```

## Architecture

```
Hetzner Cloud CCX33 ($74/mo)
├── OpenHands (AI agent runtime, port 3000)
├── LiteLLM Proxy (model gateway, port 4000)
├── Docker (agent sandboxes)
├── Tailscale (secure remote access)
├── tmux (session management)
└── Git worktrees (parallel agent workspaces)
```

**Model routing:** DeepSeek V4-Flash (primary, $0.14/M tokens) → Qwen-turbo (fallback) → Claude Haiku (emergency)

**Total cost:** $74–95/month for moderate usage (well under $200 budget)

## File Structure

```
.
├── setup.sh                    # Idempotent server setup (run as root)
├── docker-compose.yml          # Service definitions
├── .env.example                # Template for secrets
├── config/
│   ├── litellm_config.yaml     # Model routing configuration
│   └── Caddyfile               # Optional HTTPS reverse proxy
├── operations.md               # Day-to-day operations guide
├── backup.md                   # Backup, restore, pause/resume
├── provider-comparison.md      # Infrastructure & API comparison
├── cost-model.md               # Budget projections
├── recommended-architecture.md # Architecture decisions
├── provisioning-plan.md        # Step-by-step provisioning
└── risks-and-mitigations.md    # Risk analysis
```

## Requirements

- **Server:** 8+ vCPUs, 32+ GB RAM, Ubuntu 24.04 LTS
- **API keys:** DeepSeek (required), DashScope/Anthropic/OpenAI (optional)
- **Tailscale account:** Free at https://tailscale.com

## Key Operations

| Task | Command |
|------|---------|
| Start services | `cd ~/ai-workstation && docker compose up -d` |
| Stop services | `cd ~/ai-workstation && docker compose down` |
| View logs | `docker compose logs -f` |
| Check health | `curl localhost:4000/health` |
| Start tmux sessions | `~/ai-workstation/scripts/start-sessions.sh` |
| Pause workstation | See [backup.md](backup.md#pauseresume) |
| Resume workstation | See [backup.md](backup.md#pauseresume) |

## Pause/Resume (Cost Saving)

When not in use, you can pause the workstation to save costs:

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

- **Network:** Tailscale-only access (no public ports except SSH)
- **SSH:** Key-only authentication, fail2ban enabled
- **Secrets:** `.env` file (600 permissions, never committed)
- **Docker:** Agent sandboxes isolated from host
- **Updates:** Automatic security patches via unattended-upgrades

## License

Private repository. Not for redistribution.
