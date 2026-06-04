#!/usr/bin/env bash
# install-service.sh — Install the workstation systemd service
#
# Run this once after initial server setup:
#   sudo bash /opt/workstation/scripts/install-service.sh
#
# After installation, the workstation will auto-start on every boot.

set -euo pipefail

SCRIPTS_DIR="/opt/workstation/scripts"
SERVICE_NAME="workstation"

echo "==== Installing AI Workstation Service ===="
echo ""

# Copy scripts
echo "[1/4] Installing scripts..."
cp "${SCRIPTS_DIR}/workstation-startup.sh" /usr/local/bin/workstation-startup.sh
cp "${SCRIPTS_DIR}/workstation-shutdown.sh" /usr/local/bin/workstation-shutdown.sh
chmod +x /usr/local/bin/workstation-startup.sh
chmod +x /usr/local/bin/workstation-shutdown.sh
echo "  Scripts installed to /usr/local/bin/"

# Install systemd service
echo "[2/4] Installing systemd service..."
cp "${SCRIPTS_DIR}/workstation.service" /etc/systemd/system/${SERVICE_NAME}.service
systemctl daemon-reload
echo "  Service file installed"

# Enable service
echo "[3/4] Enabling service..."
systemctl enable ${SERVICE_NAME}
echo "  Service enabled (will start on boot)"

# Start now
echo "[4/4] Starting service..."
systemctl start ${SERVICE_NAME}

echo ""
echo "==== Installation Complete ===="
echo ""
echo "The workstation will now auto-start on every boot."
echo ""
echo "Management commands:"
echo "  sudo systemctl status workstation    # Check status"
echo "  sudo systemctl restart workstation   # Restart all services"
echo "  sudo systemctl stop workstation      # Stop all services"
echo "  journalctl -u workstation -f         # View logs"
echo ""
echo "Startup log: /opt/workstation/logs/startup-*.log"
