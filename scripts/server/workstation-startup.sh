#!/usr/bin/env bash
# workstation-startup.sh — Automated startup for the AI Workstation
#
# This script is designed to run at boot via systemd or manually.
# It brings up all workstation services in the correct order.
#
# Install as systemd service:
#   sudo cp /opt/workstation/scripts/workstation-startup.sh /usr/local/bin/
#   sudo chmod +x /usr/local/bin/workstation-startup.sh
#   sudo cp /opt/workstation/scripts/workstation.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable workstation
#   sudo systemctl start workstation
#
# Manual run:
#   sudo /opt/workstation/scripts/workstation-startup.sh

set +e

# --- Configuration ---
WORKSTATION_DIR="/opt/workstation"
DOCKER_COMPOSE_DIR="/home/agent/ai-workstation"
LOG_DIR="${WORKSTATION_DIR}/logs"
API_PORT=9877
LITELLM_PORT=4000
OPENHANDS_PORT=3000

# --- Logging ---
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/startup-$(date +%Y%m%d-%H%M%S).log"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo "$msg" | tee -a "$LOG_FILE" >&2
}

# --- Health Check Helpers ---
wait_for_port() {
    local port=$1
    local name=$2
    local timeout=${3:-30}
    local elapsed=0
    
    while ! ss -tlnp | grep -q ":${port} " && [ $elapsed -lt $timeout ]; do
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    if ss -tlnp | grep -q ":${port} "; then
        log "  $name is listening on port $port"
        return 0
    else
        log_error "  $name failed to start on port $port (timeout ${timeout}s)"
        return 1
    fi
}

# --- Step 1: System checks ---
log "==== AI Workstation Startup ===="
log "Host: $(hostname)"
log "Uptime: $(uptime -p)"
log "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
log "RAM: $(free -h | awk '/^Mem:/{print $3 "/" $2}')"

# --- Step 2: Ensure directories exist ---
log ""
log "[1/6] Verifying directory structure..."
for dir in sessions repos knowledge bench-apps bench-tasks bench-scripts bench-results logs; do
    mkdir -p "${WORKSTATION_DIR}/${dir}"
done
log "  Directories OK"

# --- Step 3: Start Docker ---
log ""
log "[2/6] Starting Docker..."
if ! systemctl is-active --quiet docker; then
    systemctl start docker
    sleep 2
fi
if systemctl is-active --quiet docker; then
    log "  Docker is running"
else
    log_error "  Docker failed to start"
fi

# --- Step 4: Start Docker Compose services (LiteLLM + OpenHands) ---
log ""
log "[3/6] Starting Docker Compose services..."
if [ -f "${DOCKER_COMPOSE_DIR}/docker-compose.yml" ]; then
    if [ -f "${DOCKER_COMPOSE_DIR}/.env" ] && grep -q "DEEPSEEK_API_KEY=sk-" "${DOCKER_COMPOSE_DIR}/.env" 2>/dev/null; then
        cd "$DOCKER_COMPOSE_DIR"
        docker compose up -d >> "$LOG_FILE" 2>&1
        
        # Wait for services
        wait_for_port $LITELLM_PORT "LiteLLM" 30 || true
        wait_for_port $OPENHANDS_PORT "OpenHands" 60 || true
    else
        log "  Skipped — .env not configured (no API keys)"
        log "  To configure: edit ${DOCKER_COMPOSE_DIR}/.env"
    fi
else
    log "  Skipped — docker-compose.yml not found"
fi

# --- Step 5: Start Control Plane API ---
log ""
log "[4/6] Starting Control Plane API..."
# Kill existing instance
pkill -f "uvicorn.*server" 2>/dev/null || true
sleep 1

if [ -f "${WORKSTATION_DIR}/control-plane/api/server.py" ]; then
    cd "${WORKSTATION_DIR}/control-plane"
    nohup python3 api/server.py >> "${LOG_DIR}/api.log" 2>&1 &
    API_PID=$!
    log "  API started (PID: $API_PID)"
    wait_for_port $API_PORT "Control Plane API" 10 || true
else
    log_error "  server.py not found at ${WORKSTATION_DIR}/control-plane/api/server.py"
fi

# --- Step 6: Verify xRDP ---
log ""
log "[5/6] Verifying xRDP..."
if systemctl is-active --quiet xrdp; then
    log "  xRDP is running (port 3389)"
else
    systemctl start xrdp 2>/dev/null || true
    if systemctl is-active --quiet xrdp; then
        log "  xRDP started"
    else
        log_error "  xRDP failed to start"
    fi
fi

# --- Step 7: Verify firewall ---
log ""
log "[6/6] Verifying firewall..."
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    # Ensure critical ports are open
    ufw allow 22/tcp >/dev/null 2>&1
    ufw allow 3389/tcp >/dev/null 2>&1
    ufw allow $API_PORT/tcp >/dev/null 2>&1
    log "  Firewall active — ports 22, 3389, $API_PORT open"
else
    log "  Firewall not active or not installed"
fi

# --- Summary ---
log ""
log "==== Startup Complete ===="
log ""
log "Services:"
log "  xRDP Desktop:     port 3389  (agent / <rdp-password>)"
log "  Control Plane:    port $API_PORT  (http://$(hostname -I | awk '{print $1}'):$API_PORT)"

if ss -tlnp | grep -q ":${LITELLM_PORT} "; then
    log "  LiteLLM:          port $LITELLM_PORT  (running)"
else
    log "  LiteLLM:          port $LITELLM_PORT  (not started — configure .env)"
fi

if ss -tlnp | grep -q ":${OPENHANDS_PORT} "; then
    log "  OpenHands:        port $OPENHANDS_PORT  (running)"
else
    log "  OpenHands:        port $OPENHANDS_PORT  (not started — configure .env)"
fi

log ""
log "Benchmark: $(python3 ${WORKSTATION_DIR}/bench-scripts/run-benchmark.py list 2>/dev/null | tail -1 || echo 'not available')"
log ""
log "Log file: $LOG_FILE"
