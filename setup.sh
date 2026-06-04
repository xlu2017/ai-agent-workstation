#!/usr/bin/env bash
# setup.sh — Idempotent setup for AI coding agent workstation
# Target: Hetzner Cloud CCX33 (Ubuntu 24.04 LTS) or any Ubuntu 24.04 server
# Run as root: curl -sSL <url> | bash  OR  sudo bash setup.sh
#
# This script is infrastructure-agnostic: works on Hetzner Cloud, Hetzner Dedicated,
# OVHcloud, DigitalOcean, or any Ubuntu 24.04 machine with 8+ vCPUs and 16+ GB RAM.
#
# Network policy: this script deliberately does not install or manage ufw/fail2ban.
# Restrict public ingress with the cloud/provider firewall and Tailscale ACLs/grants.

set -euo pipefail

# --- Configuration ---
AGENT_USER="${AGENT_USER:-agent}"
WORKSTATION_DIR="/home/${AGENT_USER}/ai-workstation"
DOCKER_COMPOSE_VERSION="v2.29.1"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $*"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $*" >&2; }

restart_ssh() {
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true
}

# --- Pre-flight checks ---
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (or with sudo)"
    exit 1
fi

log "Starting AI workstation setup on $(hostname)"
log "Target user: ${AGENT_USER}"

# --- Step 1: System update ---
log "Step 1/10: Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# --- Step 2: Create agent user ---
log "Step 2/10: Creating user '${AGENT_USER}'..."
if id "${AGENT_USER}" &>/dev/null; then
    log "User '${AGENT_USER}' already exists, skipping"
else
    adduser --disabled-password --gecos "" "${AGENT_USER}"
    usermod -aG sudo "${AGENT_USER}"
    # Allow sudo without password for initial setup
    echo "${AGENT_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${AGENT_USER}"
    chmod 440 "/etc/sudoers.d/${AGENT_USER}"
fi

# --- Step 3: Install core packages ---
log "Step 3/10: Installing core packages..."
apt-get install -y -qq \
    git tmux htop ncdu curl wget jq unzip \
    build-essential python3 python3-pip python3-venv \
    ca-certificates gnupg lsb-release \
    software-properties-common \
    apt-transport-https \
    chromium-browser \
    xfce4 xfce4-goodies xrdp dbus-x11 \
    unattended-upgrades

# --- Step 4: Install Docker ---
log "Step 4/10: Installing Docker..."
if command -v docker &>/dev/null; then
    log "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi
usermod -aG docker "${AGENT_USER}" 2>/dev/null || true

# Ensure Docker Compose plugin is available
if ! docker compose version &>/dev/null; then
    log "Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi
log "Docker Compose: $(docker compose version)"

# --- Step 5: Install Node.js (LTS) ---
log "Step 5/10: Installing Node.js LTS..."
if command -v node &>/dev/null; then
    log "Node.js already installed: $(node --version)"
else
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

# --- Step 6: Install Tailscale ---
log "Step 6/10: Installing Tailscale..."
if command -v tailscale &>/dev/null; then
    log "Tailscale already installed"
else
    curl -fsSL https://tailscale.com/install.sh | sh
    log "Tailscale installed. Run 'sudo tailscale up' to authenticate."
fi

# --- Step 7: Network access policy ---
log "Step 7/10: Recording network access policy..."
warn "No host firewall or fail2ban policy is configured by this script."
warn "Restrict public ingress with the provider firewall and Tailscale ACLs/grants."
warn "Recommended public ingress: none, or temporary SSH only for break-glass recovery."
warn "Run scripts/server/configure-tailscale-ssh-only.sh after Tailscale is authenticated to make tailnet port 22 Tailscale-only."

# --- Step 8: Configure SSH hardening ---
log "Step 8/10: Hardening OpenSSH..."
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
restart_ssh

# --- Step 9: Configure remote desktop ---
log "Step 9/10: Configuring xrdp..."
systemctl enable xrdp
# Set xfce4 as default session
su - "${AGENT_USER}" -c 'echo "xfce4-session" > ~/.xsession' 2>/dev/null || true
warn "xRDP is not exposed by this script. Allow it only through Tailscale or the provider firewall when needed."

# --- Step 10: Create workstation directory structure ---
log "Step 10/10: Setting up workstation directory..."
sudo -u "${AGENT_USER}" mkdir -p "${WORKSTATION_DIR}"/{config,data,logs,scripts,backups}
sudo -u "${AGENT_USER}" mkdir -p "/home/${AGENT_USER}/projects"

# Copy docker-compose and config files if they exist in same directory as this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/docker-compose.yml" ]]; then
    cp "${SCRIPT_DIR}/docker-compose.yml" "${WORKSTATION_DIR}/docker-compose.yml"
    chown "${AGENT_USER}:${AGENT_USER}" "${WORKSTATION_DIR}/docker-compose.yml"
    log "Copied docker-compose.yml"
fi
if [[ -f "${SCRIPT_DIR}/.env.example" ]]; then
    if [[ ! -f "${WORKSTATION_DIR}/.env" ]]; then
        cp "${SCRIPT_DIR}/.env.example" "${WORKSTATION_DIR}/.env"
        chown "${AGENT_USER}:${AGENT_USER}" "${WORKSTATION_DIR}/.env"
        chmod 600 "${WORKSTATION_DIR}/.env"
        warn ".env created from template — edit it with your API keys before starting services"
    fi
fi

# --- Enable unattended security updates ---
log "Enabling unattended security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# --- Create session management script ---
cat > "${WORKSTATION_DIR}/scripts/start-sessions.sh" << 'SCRIPT'
#!/bin/bash
# Start tmux sessions for agent management
set -e

SESSION_PREFIX="ws"

# Kill existing sessions if requested
if [[ "${1:-}" == "--restart" ]]; then
    tmux kill-server 2>/dev/null || true
    sleep 1
fi

# Monitor session
if ! tmux has-session -t "${SESSION_PREFIX}-monitor" 2>/dev/null; then
    tmux new-session -d -s "${SESSION_PREFIX}-monitor" 'htop'
fi

# Logs session
if ! tmux has-session -t "${SESSION_PREFIX}-logs" 2>/dev/null; then
    tmux new-session -d -s "${SESSION_PREFIX}-logs" \
        "cd ~/ai-workstation && docker compose logs -f"
fi

# Dev session
if ! tmux has-session -t "${SESSION_PREFIX}-dev" 2>/dev/null; then
    tmux new-session -d -s "${SESSION_PREFIX}-dev" \
        "cd ~/projects && bash"
fi

echo "tmux sessions created:"
tmux list-sessions
echo ""
echo "Attach with: tmux attach -t <name>"
SCRIPT
chmod +x "${WORKSTATION_DIR}/scripts/start-sessions.sh"
chown -R "${AGENT_USER}:${AGENT_USER}" "${WORKSTATION_DIR}/scripts"

# --- Create service startup script ---
cat > "${WORKSTATION_DIR}/scripts/start-services.sh" << 'SCRIPT'
#!/bin/bash
# Start the AI workstation services
set -e
cd ~/ai-workstation

if [[ ! -f .env ]]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in your API keys."
    exit 1
fi

# Validate required env vars
source .env
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    echo "ERROR: DEEPSEEK_API_KEY not set in .env"
    exit 1
fi

echo "Starting services..."
docker compose up -d

echo "Waiting for services to be healthy..."
sleep 5

echo "Checking service health..."
if curl -sf http://localhost:4000/health > /dev/null 2>&1; then
    echo "✓ LiteLLM Proxy is healthy (port 4000)"
else
    echo "✗ LiteLLM Proxy not responding"
fi

if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "✓ OpenHands is healthy (port 3000)"
else
    echo "✗ OpenHands not responding (may need more startup time)"
fi

echo ""
echo "Services running. Access:"
echo "  OpenHands UI: http://localhost:3000"
echo "  LiteLLM Admin: http://localhost:4000/ui"
echo "  Use SSH port forwarding or Tailscale; do not expose admin ports publicly."
SCRIPT
chmod +x "${WORKSTATION_DIR}/scripts/start-services.sh"
chown -R "${AGENT_USER}:${AGENT_USER}" "${WORKSTATION_DIR}/scripts"

# --- Final summary ---
echo ""
echo "============================================"
log "AI Workstation setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Copy your SSH public key to /home/${AGENT_USER}/.ssh/authorized_keys before relying on public SSH"
echo "  2. Run: sudo tailscale up"
echo "  3. Configure Tailscale ACLs/grants and the provider firewall; this script does not manage ufw/fail2ban"
echo "  4. Run: sudo ${SCRIPT_DIR}/scripts/server/configure-tailscale-ssh-only.sh after confirming Tailscale access"
echo "  5. Edit ${WORKSTATION_DIR}/.env with your API keys"
echo "  6. Run: su - ${AGENT_USER} -c '${WORKSTATION_DIR}/scripts/start-services.sh'"
echo "  7. Access OpenHands through SSH forwarding or the Tailscale hostname"
echo ""
echo "System info:"
echo "  CPU: $(nproc) cores"
echo "  RAM: $(free -h | awk '/Mem:/{print $2}')"
echo "  Disk: $(df -h / | awk 'NR==2{print $4}') free"
echo "  Docker: $(docker --version)"
echo "  Node.js: $(node --version)"
echo ""