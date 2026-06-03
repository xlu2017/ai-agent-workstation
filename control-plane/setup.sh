#!/bin/bash
# Reproducible setup script for the workstation control plane.
# Run on a fresh Ubuntu 24.04 server to get everything running.
# Idempotent — safe to re-run.
set -euo pipefail

echo "=== Workstation Control Plane Setup ==="
echo "Target: $(hostname) — $(date -u)"

WORKSTATION_ROOT="/opt/workstation"
CONTROL_PLANE="$WORKSTATION_ROOT/control-plane"

# --- 1. Directory structure ---
echo "[1/8] Creating directory structure..."
mkdir -p "$WORKSTATION_ROOT"/{repos,sessions,knowledge/proposed,logs,backups,scripts,config}
mkdir -p "$CONTROL_PLANE"/{api,cli,core,web,tests}

# --- 2. System dependencies ---
echo "[2/8] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git tmux ripgrep fd-find jq curl wget unzip htop ncdu \
  python3 python3-pip python3-venv nodejs npm docker.io docker-compose-plugin 2>/dev/null || true

# --- 3. Python packages ---
echo "[3/8] Installing Python packages..."
pip install --break-system-packages --quiet fastapi uvicorn pyyaml pydantic 2>/dev/null || \
  pip install --quiet fastapi uvicorn pyyaml pydantic

# --- 4. Node packages (dashboard) ---
echo "[4/8] Building web dashboard..."
if [ -f "$CONTROL_PLANE/web/package.json" ]; then
  cd "$CONTROL_PLANE/web"
  npm install --silent 2>/dev/null
  npx vite build 2>/dev/null
  echo "  Dashboard built at $CONTROL_PLANE/web/dist/"
fi

# --- 5. CLI setup ---
echo "[5/8] Installing platformctl CLI..."
chmod +x "$CONTROL_PLANE/cli/platformctl.py" 2>/dev/null || true
ln -sf "$CONTROL_PLANE/cli/platformctl.py" /usr/local/bin/platformctl 2>/dev/null || true

# --- 6. systemd services ---
echo "[6/8] Installing systemd services..."

cat > /etc/systemd/system/control-plane.service << 'EOF'
[Unit]
Description=Workstation Control Plane API
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=agent
WorkingDirectory=/opt/workstation/control-plane/api
Environment=SESSIONS_DIR=/opt/workstation/sessions
Environment=KNOWLEDGE_DIR=/opt/workstation/knowledge
Environment=LITELLM_URL=http://localhost:4000
Environment=OPENHANDS_URL=http://localhost:3000
Environment=BRIDGE_URL=http://localhost:9876
ExecStart=/usr/bin/python3 server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/ui-bridge.service << 'EOF'
[Unit]
Description=UI Bridge Service (context routing)
After=network.target

[Service]
Type=simple
User=agent
WorkingDirectory=/opt/workstation/glue/ui-bridge
Environment=SESSIONS_DIR=/opt/workstation/sessions
ExecStart=/usr/bin/python3 server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable control-plane.service ui-bridge.service 2>/dev/null || true

# --- 7. Backup cron ---
echo "[7/8] Setting up backup cron..."
cat > /etc/cron.d/workstation-backup << 'EOF'
# Daily backup at 3 AM UTC
0 3 * * * agent /opt/workstation/control-plane/cli/platformctl.py backup 2>&1 | logger -t workstation-backup
EOF

# --- 8. Verify ---
echo "[8/8] Verifying installation..."
echo "  platformctl: $(which platformctl 2>/dev/null || echo 'NOT FOUND')"
echo "  python3: $(python3 --version)"
echo "  node: $(node --version 2>/dev/null || echo 'NOT FOUND')"
echo "  docker: $(docker --version 2>/dev/null || echo 'NOT FOUND')"
echo "  sessions dir: $(ls -d $WORKSTATION_ROOT/sessions 2>/dev/null || echo 'MISSING')"

echo ""
echo "=== Setup Complete ==="
echo "Start services:"
echo "  systemctl start control-plane"
echo "  systemctl start ui-bridge"
echo ""
echo "Access dashboard:"
echo "  http://localhost:9877"
echo ""
echo "Run doctor check:"
echo "  platformctl doctor"
