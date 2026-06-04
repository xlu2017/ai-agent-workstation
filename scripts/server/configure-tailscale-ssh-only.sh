#!/usr/bin/env bash
# configure-tailscale-ssh-only.sh — block all network OpenSSH access except Tailscale SSH.
#
# Purpose:
#   - Enable Tailscale SSH on this machine.
#   - Remove ordinary OpenSSH from all network-facing interfaces.
#   - Retain ordinary OpenSSH only as a localhost console fallback on 127.0.0.1:2222.
#   - Leave public ingress enforcement to the cloud/provider firewall.
#
# Result:
#   - Tailnet port 22 is handled by Tailscale SSH.
#   - Ordinary OpenSSH is not reachable from the public internet or LAN.
#   - Ordinary OpenSSH is available only from the server itself at 127.0.0.1:2222.
#   - Public SSH on <public-ip>:22 must also be blocked at the provider firewall.
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

assert_no_network_openssh() {
    local bad_listeners
    bad_listeners="$(ss -tlnp 2>/dev/null | awk '
        /sshd/ && /:22[[:space:]]/ && $4 !~ /^127\.0\.0\.1:2222$/ && $4 !~ /^\[::1\]:2222$/ { print }
        /sshd/ && /:2222[[:space:]]/ && $4 !~ /^127\.0\.0\.1:2222$/ && $4 !~ /^\[::1\]:2222$/ { print }
    ' || true)"

    if [[ -n "$bad_listeners" ]]; then
        error "OpenSSH is still listening on a non-loopback address:"
        echo "$bad_listeners" >&2
        error "Restoring backup to avoid leaving an ambiguous SSH state."
        cp "$BACKUP" "$SSHD_CONFIG"
        restart_ssh
        exit 1
    fi
}

if [[ $EUID -ne 0 ]]; then
    error "Run as root: sudo $0"
    exit 1
fi

if ! command -v tailscale >/dev/null 2>&1; then
    error "tailscale is not installed. Run setup.sh first."
    exit 1
fi

if ! command -v ss >/dev/null 2>&1; then
    error "ss command not found; install iproute2 before running this script."
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

log "Removing ordinary OpenSSH from network-facing interfaces"
# Remove existing ListenAddress/Port lines that would keep public or LAN SSH open.
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
assert_no_network_openssh

log "Non-Tailscale network SSH is blocked at the host: OpenSSH is localhost-only on 127.0.0.1:2222."
log "Tailscale SSH should handle tailnet access on ${TAILSCALE_IP}:22."
log "Now enforce the same policy at the provider firewall: block public TCP/22 and all other admin ports unless intentionally public."
log "Test from an admin device: ssh agent@${TAILSCALE_IP}"
log "Expected failure from outside the tailnet: ssh agent@<server-public-ip>"
