# Operations Guide

Day-to-day operations for the AI coding agent workstation.

---

## Service Management

### Start all services

```bash
cd ~/ai-workstation
docker compose up -d
```

### Stop all services

```bash
cd ~/ai-workstation
docker compose down
```

### Restart a single service

```bash
docker compose restart litellm
docker compose restart openhands
```

### View logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f litellm
docker compose logs -f openhands

# Last 100 lines
docker compose logs --tail=100 litellm
```

### Check health

```bash
# LiteLLM
curl -s http://localhost:4000/health | jq .

# OpenHands
curl -s http://localhost:3000

# All containers
docker compose ps
```

---

## Model Management

### Test a model via LiteLLM

```bash
curl -s http://localhost:4000/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Hello, respond with one word."}]
  }' | jq .choices[0].message.content
```

### Switch primary model

Edit `config/litellm_config.yaml`, then:

```bash
docker compose restart litellm
```

### Check API spend

LiteLLM tracks costs per model. View at: `http://localhost:4000/ui`

### Add a new model provider

1. Add API key to `.env`
2. Add model entry to `config/litellm_config.yaml`
3. `docker compose restart litellm`

---

## Session Management

### tmux basics

```bash
# Start all sessions
~/ai-workstation/scripts/start-sessions.sh

# List sessions
tmux list-sessions

# Attach to a session
tmux attach -t ws-dev

# Detach from session (inside tmux)
Ctrl+B, then D

# Create new named session
tmux new-session -s my-project

# Kill a session
tmux kill-session -t my-project
```

### Git worktrees for parallel agents

```bash
cd ~/projects

# Clone as bare repo (one-time)
git clone --bare https://github.com/user/repo.git repo.git

# Create worktrees for parallel work
git -C repo.git worktree add ../repo-main main
git -C repo.git worktree add ../repo-feature-1 -b feature/new-api
git -C repo.git worktree add ../repo-bugfix-2 -b fix/memory-leak

# List worktrees
git -C repo.git worktree list

# Remove a worktree when done
git -C repo.git worktree remove ../repo-feature-1
```

---

## Docker Management

### View resource usage

```bash
docker stats --no-stream
```

### Clean up old images/containers

```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -f

# Remove everything unused (careful!)
docker system prune -f

# Check disk usage
docker system df
```

### Update service images

```bash
cd ~/ai-workstation

# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d

# If issues, roll back:
# docker compose down
# docker compose up -d --force-recreate
```

---

## System Maintenance

### Disk usage

```bash
# Overview
df -h

# Find large directories
ncdu /home/agent

# Docker disk usage
docker system df
```

### Memory usage

```bash
free -h
# Or for detailed view:
htop
```

### System updates

Security updates are applied automatically. For manual full update:

```bash
sudo apt update && sudo apt upgrade -y
```

### Check for reboot-required

```bash
if [ -f /var/run/reboot-required ]; then
    echo "Reboot required"
    cat /var/run/reboot-required.pkgs
fi
```

---

## Tailscale

### Check status

```bash
tailscale status
```

### Get hostname/IP

```bash
tailscale ip -4
tailscale status | grep $(hostname)
```

### Re-authenticate (if expired)

```bash
sudo tailscale up
# Follow the URL to re-auth
```

---

## Troubleshooting

### LiteLLM not responding

```bash
# Check if container is running
docker compose ps litellm

# Check logs for errors
docker compose logs --tail=50 litellm

# Common issues:
# - Invalid API key in .env
# - Malformed litellm_config.yaml
# - Port 4000 already in use

# Fix: validate config
docker compose exec litellm python -c "import yaml; yaml.safe_load(open('/app/config.yaml'))"

# Restart
docker compose restart litellm
```

### OpenHands not starting

```bash
# Check logs
docker compose logs --tail=50 openhands

# Common issues:
# - Docker socket not accessible
# - LiteLLM not healthy yet (dependency)
# - Insufficient RAM

# Fix: ensure docker socket is accessible
ls -la /var/run/docker.sock

# Restart
docker compose restart openhands
```

### High memory usage

```bash
# Check what's using memory
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"

# If agent sandboxes are leaking:
docker ps --filter "name=openhands-sandbox" --format "{{.Names}}: {{.Status}}"

# Kill orphaned sandboxes
docker ps --filter "name=openhands-sandbox" -q | xargs docker rm -f
```

### SSH connection issues

```bash
# Check SSH service
sudo systemctl status sshd

# Check firewall
sudo ufw status

# Check fail2ban (your IP might be banned)
sudo fail2ban-client status sshd

# Unban an IP
sudo fail2ban-client set sshd unbanip <your-ip>
```

### DeepSeek API errors

```bash
# Test direct API access (bypassing LiteLLM)
curl -s https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}]}' | jq .

# If 503/429: DeepSeek is congested. Fallback models should engage automatically.
# If 401: API key is invalid. Regenerate at https://platform.deepseek.com
```

---

## Useful Aliases

Add to `~/.bashrc`:

```bash
# AI Workstation shortcuts
alias ws='cd ~/ai-workstation'
alias wsu='cd ~/ai-workstation && docker compose up -d'
alias wsd='cd ~/ai-workstation && docker compose down'
alias wsl='cd ~/ai-workstation && docker compose logs -f'
alias wss='docker compose -f ~/ai-workstation/docker-compose.yml ps'
alias wsr='cd ~/ai-workstation && docker compose restart'

# tmux shortcuts
alias ta='tmux attach -t'
alias tl='tmux list-sessions'
alias tn='tmux new-session -s'
```
