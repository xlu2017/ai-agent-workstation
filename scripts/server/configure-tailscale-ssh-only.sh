#!/usr/bin/env bash
# configure-tailscale-ssh-only.sh — move administrative SSH access to Tailscale SSH.
#
# Purpose:
#   - Enable Tailscale SSH on this machine.
#   - Move ordinary OpenSSH off public port 22 by binding it to localhost:2222.
#   - Leave public ingress enforcement to the cloud/provider firewall.
#
# Result:
#   - Tailnet port 22 is handled by Tailscale SSH.
#   - Ordinary SSH is available only from the server itself at 127.0.0.1:2222.
#   - Public SSH on <public-ip>:22 should be blocked at the provider firewall.
#
# Safety:
#   Run this only after confirming this machine is authenticated to Tailscale and
#   reachable from an admin device in the same tailnet.

set -euo pipefail

SSHD_CONFIG="/etc/ssh/sshd_config"
BACKUP="${SSHD_CONFIG}.pre-tailscale-ssh-only.$(date +%Y%m%d-%H%M%S)"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

restart_ssh() {
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
}

if [[ $EUID -ne 0 ]]; then
    error "Run as root: sudo $0"
    exit 1
fi

if ! command -v tailscale >/dev/null 2>&1; then
    error "tailscale is not installed. Run setup.sh first."
    exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
    error "tailscale is installed but not authenticated. Run 'sudo tailscale up' first."
    exit 1
fi

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
if [[ -z "$TAILSCALE_IP" ]]; then
    error "could not determine this machine's Tailscale IPv4 address."
    exit 1
fi

log "Tailscale IP detected: $TAILSCALE_IP"
log "Enabling Tailscale SSH. Confirm tailnet ACLs/grants allow the intended admin users."

# Preserve current auth/session state while enabling the SSH feature.
# If this fails because tailscale requires re-authentication or extra flags, run the
# printed command manually from the provider console.
tailscale set --ssh=true 2>/dev/null || tailscale up --ssh

log "Backing up $SSHD_CONFIG to $BACKUP"
cp "$SSHD_CONFIG" "$BACKUP"

log "Moving ordinary OpenSSH to localhost:2222"
# Remove existing ListenAddress/Port lines managed by this script or defaults that would keep public :22 open.
sed -i '/^#\?Port /d' "$SSHD_CONFIG"
sed -i '/^#\?ListenAddress /d' "$SSHD_CONFIG"

cat >> "$SSHD_CONFIG" <<'EOF'

# Managed by configure-tailscale-ssh-only.sh
# Tailscale SSH handles tailnet port 22. Ordinary OpenSSH is retained only as
# a local break-glass endpoint reachable from the server console.
Port 2222
ListenAddress 127.0.0.1
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
EOF

if ! sshd -t; then
    error "sshd_config validation failed. Restoring backup."
    cp "$BACKUP" "$SSHD_CONFIG"
    restart_ssh
    exit 1
fi

restart_ssh

log "OpenSSH now listens on 127.0.0.1:2222 only."
log "Tailscale SSH should handle tailnet access on ${TAILSCALE_IP}:22."
log "Now enforce public ingress in the provider firewall: block public TCP/22 and all other admin ports unless intentionally public."
log "Test from an admin device: ssh agent@${TAILSCALE_IP}"
