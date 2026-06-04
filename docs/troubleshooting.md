# Troubleshooting

## Common Issues

### LiteLLM Container Unhealthy

**Symptoms:** `docker compose ps` shows litellm as `(unhealthy)`

**Diagnosis:**
```bash
docker compose logs litellm --tail=50
```

**Common causes:**
1. **curl not in container** — Healthcheck uses python urllib, not curl
2. **master_key in yaml** — Triggers PostgreSQL requirement. Keep it in env var only.
3. **Invalid API key** — Check `.env` file has correct DEEPSEEK_API_KEY

**Fix:**
```bash
# Check health endpoint directly
docker exec litellm python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:4000/health/liveliness').read())"

# Restart
docker compose restart litellm
```

### OpenHands Won't Start

**Symptoms:** Container stays in "Created" state

**Diagnosis:**
```bash
docker compose logs openhands
docker inspect openhands | jq '.[0].State'
```

**Common causes:**
1. **LiteLLM not healthy** — OpenHands depends on litellm being healthy
2. **Port conflict** — Another process on port 3000
3. **Docker socket permission** — OpenHands needs `/var/run/docker.sock`

**Fix:**
```bash
# Check port
ss -tlnp | grep 3000

# Restart both
docker compose down && docker compose up -d
```

### RDP Connection Refused

**Symptoms:** Can't connect to port 3389 over Tailscale

**Diagnosis:**
```bash
sudo systemctl status xrdp
sudo ss -tlnp | grep 3389
tailscale status
tailscale ip -4
```

**Common causes:**
1. **xrdp not running** — `sudo systemctl start xrdp`
2. **Tailscale unavailable** — authenticate with `sudo tailscale up` and verify tailnet policy
3. **Provider firewall policy** — public RDP should normally be blocked; use Tailscale or SSH forwarding instead
4. **Wrong credentials** — user: agent, password set via `sudo passwd agent`

### Tailscale SSH Not Working

**Symptoms:** `ssh agent@<tailscale-hostname>` fails after configuring Tailscale-only SSH.

**Diagnosis:**
```bash
tailscale status
tailscale ip -4
sudo tailscale debug prefs | grep -i ssh || true
sudo ss -tlnp | grep -E ':22|:2222'
sudo journalctl -u tailscaled -n 100 --no-pager
```

**Common causes:**
1. **Tailscale SSH not enabled** — run `sudo tailscale set --ssh=true` or `sudo tailscale up --ssh`
2. **ACL/grants deny access** — allow your admin identity to reach the workstation on port 22
3. **Server not authenticated** — run `sudo tailscale up` from the provider console
4. **Using public IP instead of tailnet name/IP** — connect to the Tailscale hostname or `100.x.y.z` address

**Recovery:**
```bash
# From provider console only; ordinary OpenSSH is moved to localhost:2222
ssh -p 2222 agent@127.0.0.1

# Restore the last pre-Tailscale-SSH sshd_config backup if needed
ls -1 /etc/ssh/sshd_config.pre-tailscale-ssh-only.*
sudo cp /etc/ssh/sshd_config.pre-tailscale-ssh-only.<timestamp> /etc/ssh/sshd_config
sudo systemctl restart ssh || sudo systemctl restart sshd
```

### High CPU Usage

**Diagnosis:**
```bash
htop
docker stats
```

**Common causes:**
1. **Runaway agent session** — Kill the tmux session
2. **Docker build** — Normal during image pulls/builds
3. **Chrome processes** — Kill orphan chromes: `pkill -f chrome`

### Disk Full

**Diagnosis:**
```bash
df -h /
ncdu /opt/workstation
docker system df
```

**Fix:**
```bash
# Clean Docker
docker system prune -a --volumes

# Clean old worktrees
./scripts/list-worktrees.sh
./scripts/destroy-worktree.sh <old-worktree>

# Clean BorgBackup
borg prune --keep-daily=7 --keep-weekly=4 /opt/workstation/backups/main
borg compact /opt/workstation/backups/main
```

### API Calls Failing (402/429)

**Symptoms:** LiteLLM returns 402 (payment required) or 429 (rate limited)

**Diagnosis:**
```bash
# Check DeepSeek balance
curl -s https://api.deepseek.com/user/balance \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" | jq .

# Check LiteLLM budget
curl -s http://localhost:4000/budget/info \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq .
```

**Fix:**
- Top up at https://platform.deepseek.com/top_up
- Adjust budget limits in `config/litellm_config.yaml`

### BorgBackup Errors

**Common issues:**
```bash
# Lock file stuck (after crash)
borg break-lock /opt/workstation/backups/main

# Check repository integrity
borg check /opt/workstation/backups/main

# List archives
borg list /opt/workstation/backups/main
```

## Service Recovery

### Full restart (all services):
```bash
cd ~/ai-workstation
docker compose down
docker compose up -d
```

### Restore from backup:
```bash
# List available backups
borg list /opt/workstation/backups/main

# Restore specific path
cd /opt/workstation
borg extract /opt/workstation/backups/main::ARCHIVE_NAME repos/

# Restore everything
borg extract /opt/workstation/backups/main::ARCHIVE_NAME
```

## Log Locations

| Service | Log Location |
|---------|-------------|
| LiteLLM | `docker compose logs litellm` |
| OpenHands | `docker compose logs openhands` |
| xRDP | `/var/log/xrdp.log` |
| Tailscale | `journalctl -u tailscaled` |
| System | `journalctl -xe` |
| Worktrees | `/opt/workstation/logs/worktrees.log` |
| Backups | `/opt/workstation/logs/backup.log` |
