# Operations Guide

## Daily Operations

### Start all services
```bash
cd ~/ai-workstation && docker compose up -d
```

### Check status
```bash
docker compose ps
curl -s http://localhost:4000/health/liveliness  # "I'm alive!"
curl -s http://localhost:3000 | head -1          # OpenHands HTML
```

### View logs
```bash
docker compose logs -f              # All services
docker compose logs litellm -f      # LiteLLM only
docker compose logs --tail=50       # Last 50 lines
```

### Stop all services
```bash
docker compose down
```

## Access Methods

Preferred access is Tailscale-first. The workstation does not rely on `ufw` or `fail2ban`; public ingress is controlled by the provider firewall and tailnet access is controlled by Tailscale ACLs/grants.

| Method | Command | Use Case |
|--------|---------|----------|
| Tailscale SSH | `ssh agent@<tailscale-hostname>` | Primary terminal access on tailnet port 22 |
| SSH + ports over Tailscale | `ssh -L 9877:localhost:9877 -L 4000:localhost:4000 agent@<tailscale-hostname>` | Control plane and LiteLLM UI without public exposure |
| RDP over Tailscale | Connect to `<tailscale-hostname>:3389` | GUI/browser access when enabled by Tailscale policy |
| VS Code | Remote-SSH to `<tailscale-hostname>` | Development |
| Local OpenSSH fallback | Provider console, then `ssh -p 2222 agent@127.0.0.1` | Local-only recovery after Tailscale-only SSH configuration |

### Configure Tailscale-only SSH

After confirming the server is authenticated to Tailscale and reachable from an admin device:

```bash
sudo /opt/workstation/scripts/configure-tailscale-ssh-only.sh
```

This script enables Tailscale SSH, moves ordinary OpenSSH to `127.0.0.1:2222`, and leaves public TCP/22 blocking to the provider firewall.

Provider firewall target:

```text
Public inbound: deny by default
Temporary break-glass: allow TCP/22 only when needed
Intentional public web: allow TCP/80 and TCP/443 only if serving a public app
```

## Worktree Management

### Create new agent workspace
```bash
# First time: clone as bare repo
git clone --bare https://github.com/user/repo.git /opt/workstation/repos/repo.git

# Create worktree for a feature
/opt/workstation/scripts/create-worktree.sh repo feature/my-feature main
```

### List active worktrees
```bash
/opt/workstation/scripts/list-worktrees.sh
```

### Destroy worktree
```bash
/opt/workstation/scripts/destroy-worktree.sh repo-feature-my-feature
```

## tmux Session Management

```bash
# List sessions
tmux ls

# Attach to agent session
tmux attach -t agent-repo-feature-my-feature

# Create manual session
tmux new -s dev

# Detach: Ctrl+B, then D
```

## Chrome Remote Debugging

```bash
# Launch Chrome with debugging port
google-chrome --remote-debugging-port=9222 --no-first-run --user-data-dir=/tmp/chrome-debug

# Access DevTools from local machine over Tailscale SSH forwarding
# Forward: ssh -L 9222:localhost:9222 agent@<tailscale-hostname>
# Open: http://localhost:9222
```

## LiteLLM Model Testing

```bash
# Load key
export LITELLM_MASTER_KEY=$(grep LITELLM_MASTER_KEY ~/ai-workstation/.env | cut -d= -f2)

# Test primary (DeepSeek)
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"Say hi"}],"max_tokens":10}' | jq .choices[0].message.content

# List available models
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.data[].id'
```

## Knowledge System

```bash
# Find relevant knowledge for a task
python3 /opt/workstation/scripts/knowledge-loader.py \
  --task "Create a React component" \
  --packages react typescript

# Add new knowledge file
cp /opt/workstation/knowledge/example-react.yaml /opt/workstation/knowledge/my-project.yaml
# Edit the new file with your project-specific knowledge
```

## Monitoring

```bash
# System metrics; keep exporter private and access through SSH forwarding/Tailscale only
curl -s http://localhost:9100/metrics | grep -E "^node_(cpu|memory|disk)"

# Docker resource usage
docker stats --no-stream

# Disk usage
df -h / && ncdu /opt/workstation
```

## Backup

```bash
# Manual backup now
/opt/workstation/scripts/backup-now.sh

# List backups
borg list /opt/workstation/backups/main

# Restore (see docs/backup.md for full guide)
borg extract /opt/workstation/backups/main::LATEST
```
