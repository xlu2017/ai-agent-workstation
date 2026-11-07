# Provisioning Plan

## Prerequisites

Before provisioning, ensure you have:

- [ ] Hetzner account created (https://accounts.hetzner.com)
- [ ] Payment method added to Hetzner account
- [ ] DeepSeek API account (https://platform.deepseek.com)
- [ ] DeepSeek API balance topped up ($10–50 recommended)
- [ ] Alibaba Cloud / DashScope account (https://www.alibabacloud.com/product/model-studio)
- [ ] SSH key pair generated locally
- [ ] Tailscale account (https://tailscale.com) — free for personal use
- [ ] (Optional) Anthropic API key for emergency fallback
- [ ] (Optional) Domain name for HTTPS access

---

## Phase 1: Infrastructure Provisioning

### Step 1.1: Create Hetzner Cloud CCX33

1. Navigate to https://console.hetzner.cloud
2. Create project → Add server
3. Location: **Helsinki (HEL1)** recommended (good connectivity to DeepSeek Asia + EU)
   - Alternative: Ashburn (US) if lower latency to North American services preferred
4. Image: Ubuntu 24.04
5. Type: General Purpose → **CCX33** (8 dedicated vCPU, 32 GB RAM, 240 GB NVMe)
6. SSH key: Add your public key
7. Create ($73.99/mo, available in ~30 seconds)

**Future upgrade path: Hetzner Dedicated AX42-U**
- When you confirm always-on 24/7 usage, migrate to dedicated ($59/mo, saves $15/mo)
- See `backup.md` for migration procedure

### Step 1.2: Initial Server Access

```bash
# Once server is delivered, SSH in
ssh root@<server-ip>

# Verify hardware
lscpu
free -h
lsblk
```

---

## Phase 2: Base System Configuration

### Step 2.1: System Hardening

```bash
# Update system
apt update && apt upgrade -y

# Create non-root user
adduser agent
usermod -aG sudo agent
usermod -aG docker agent

# Configure SSH
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# Install fail2ban
apt install -y fail2ban
systemctl enable fail2ban

# Configure UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw enable
```

### Step 2.2: Install Core Dependencies

```bash
# Docker (official method)
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# Docker Compose
apt install -y docker-compose-plugin

# Essential tools
apt install -y \
  git tmux htop ncdu curl wget jq \
  build-essential python3 python3-pip python3-venv \
  nodejs npm \
  chromium-browser \
  xrdp xfce4 xfce4-goodies \
  unattended-upgrades

# Verify
docker --version
docker compose version
git --version
tmux -V
```

### Step 2.3: Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
# Follow the auth URL printed to terminal
```

### Step 2.4: Configure Remote Desktop (Optional)

```bash
# xrdp is already installed above
systemctl enable xrdp
# Configure xrdp to use xfce4
echo "xfce4-session" > /home/agent/.xsession
chown agent:agent /home/agent/.xsession
```

---

## Phase 3: Application Stack Deployment

### Step 3.1: Create Project Structure

```bash
su - agent
mkdir -p ~/ai-workstation/{config,data,logs,scripts}
cd ~/ai-workstation
```

### Step 3.2: Create docker-compose.yml

See `docker-compose.yml` deliverable (created after approval).

Key services:
- `litellm` — Model proxy (port 4000)
- `openhands` — AI agent runtime (port 3000)
- `caddy` — Reverse proxy (port 443, optional)

### Step 3.3: Create LiteLLM Configuration

```yaml
# config/litellm_config.yaml
model_list:
  - model_name: "deepseek-v4-flash"
    litellm_params:
      model: "deepseek/deepseek-v4-flash"
      api_base: "https://api.deepseek.com"
      api_key: "os.environ/DEEPSEEK_API_KEY"

  - model_name: "deepseek-v4-pro"
    litellm_params:
      model: "deepseek/deepseek-v4-pro"
      api_base: "https://api.deepseek.com"
      api_key: "os.environ/DEEPSEEK_API_KEY"

  - model_name: "qwen-turbo"
    litellm_params:
      model: "openai/qwen-turbo-latest"
      api_base: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
      api_key: "os.environ/DASHSCOPE_API_KEY"

  - model_name: "claude-haiku"
    litellm_params:
      model: "claude-haiku-4.5"
      api_key: "os.environ/ANTHROPIC_API_KEY"

router_settings:
  num_retries: 3
  fallbacks:
    - deepseek-v4-flash: ["qwen-turbo", "claude-haiku"]
    - deepseek-v4-pro: ["deepseek-v4-flash", "claude-haiku"]
```

### Step 3.4: Create .env File

```bash
# .env (never committed to git)
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx  # optional
LITELLM_MASTER_KEY=sk-litellm-xxx  # generate with: openssl rand -hex 32
```

### Step 3.5: Deploy Stack

```bash
cd ~/ai-workstation
docker compose up -d

# Verify
docker compose ps
curl http://localhost:4000/health  # LiteLLM
curl http://localhost:3000         # OpenHands
```

---

## Phase 4: Git Worktree Setup

```bash
# Clone target repos as bare repositories
mkdir -p ~/projects
cd ~/projects
git clone --bare https://github.com/user/repo.git repo.git

# Create worktrees for parallel agent sessions
git -C repo.git worktree add ../repo-main main
git -C repo.git worktree add ../repo-agent1 -b agent/feature-1
git -C repo.git worktree add ../repo-agent2 -b agent/feature-2
```

---

## Phase 5: tmux Session Management

```bash
# Create session management script
cat > ~/ai-workstation/scripts/start-sessions.sh << 'EOF'
#!/bin/bash
# Start tmux sessions for agent management

tmux new-session -d -s monitor 'htop'
tmux new-session -d -s logs 'docker compose -f ~/ai-workstation/docker-compose.yml logs -f'
tmux new-session -d -s dev 'cd ~/projects && bash'

echo "Sessions created. Attach with: tmux attach -t <name>"
echo "Available: monitor, logs, dev"
EOF
chmod +x ~/ai-workstation/scripts/start-sessions.sh
```

---

## Phase 6: Verification

### Checklist

- [ ] SSH access works (non-root user, key auth only)
- [ ] Tailscale connected (can reach via Tailscale IP/hostname)
- [ ] Docker running (`docker ps` shows containers)
- [ ] LiteLLM healthy (`curl localhost:4000/health`)
- [ ] OpenHands accessible (`curl localhost:3000`)
- [ ] DeepSeek API working (test via LiteLLM: `curl localhost:4000/chat/completions`)
- [ ] Git worktrees created and functional
- [ ] tmux sessions running
- [ ] Remote desktop accessible (if configured)
- [ ] Firewall configured (only SSH + Tailscale open)
- [ ] Unattended upgrades enabled
- [ ] Backups configured

---

## Phase 7: Post-Deployment

### Enable Automatic Security Updates

```bash
dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" to enable automatic updates
```

### Set Up Backup Cron

```bash
# Daily backup of configs to Hetzner Storage Box (optional)
crontab -e
# Add: 0 3 * * * /home/agent/ai-workstation/scripts/backup.sh
```

### Document Access

```
SSH: ssh agent@<tailscale-hostname>
OpenHands UI: http://<tailscale-hostname>:3000
LiteLLM Admin: http://<tailscale-hostname>:4000/ui
Remote Desktop: rdp://<tailscale-hostname>:3389
```

---

## Timeline Estimate

| Phase | Duration | Blocking? |
|-------|----------|-----------|
| 1. Order server | 5 min | No |
| 1. Wait for delivery | 1–5 days | Yes (dedicated) / 30s (cloud) |
| 2. Base config | 30 min | No |
| 3. Application stack | 20 min | No |
| 4. Git worktrees | 10 min | No |
| 5. tmux setup | 5 min | No |
| 6. Verification | 15 min | No |
| **Total (after delivery)** | **~90 min** | |

---

## Rollback Plan

If issues arise:
1. **Cloud option:** Delete server, recreate from snapshot (if taken)
2. **Dedicated option:** Reinstall OS via Hetzner Robot rescue system (takes ~15 min)
3. **Full rollback:** Cancel server within 14-day cooling period (dedicated setup fee is non-refundable)
