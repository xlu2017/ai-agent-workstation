#!/usr/bin/env bash
# workstation-startup.sh — Fully automated startup for the AI Workstation
#
# Handles both first-time provisioning and subsequent boots.
# Installs missing packages, builds the dashboard, starts all services.
#
# Install as systemd service:
#   sudo bash /opt/workstation/scripts/install-service.sh
#
# Manual run:
#   sudo /opt/workstation/scripts/workstation-startup.sh
#
# Network policy:
#   This script deliberately does not manage ufw/fail2ban or provider firewall rules.
#   Public ingress must be controlled by the cloud/provider firewall and Tailscale ACLs/grants.

set +e

# --- Configuration ---
WORKSTATION_DIR="/opt/workstation"
DOCKER_COMPOSE_DIR="/home/agent/ai-workstation"
LOG_DIR="${WORKSTATION_DIR}/logs"
WEB_DIR="${WORKSTATION_DIR}/control-plane/web"
API_PORT=9877
LITELLM_PORT=4000
OPENHANDS_PORT=3000
DASHBOARD_PORT=$API_PORT

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

# --- Port Allocation ---
find_free_port() {
    local start=${1:-3010}
    local end=${2:-3099}
    local port=$start
    while [ $port -le $end ]; do
        if ! ss -tlnp | grep -q ":${port} "; then
            echo $port
            return 0
        fi
        port=$((port + 1))
    done
    echo $start
    return 1
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

# ============================================================
# STEP 1: System checks
# ============================================================
log "==== AI Workstation Startup ===="
log "Host: $(hostname)"
log "Uptime: $(uptime -p)"
log "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
log "RAM: $(free -h | awk '/^Mem:/{print $3 "/" $2}')"

# ============================================================
# STEP 2: Directory structure
# ============================================================
log ""
log "[1/8] Verifying directory structure..."
for dir in sessions repos knowledge bench-apps bench-tasks bench-scripts bench-results logs; do
    mkdir -p "${WORKSTATION_DIR}/${dir}"
done
log "  Directories OK"

# ============================================================
# STEP 3: Install missing packages (first-time only)
# ============================================================
log ""
log "[2/8] Checking required packages..."

install_if_missing() {
    local cmd=$1
    local pkg=${2:-$1}
    if ! command -v "$cmd" &>/dev/null; then
        log "  Installing $pkg..."
        apt-get install -y "$pkg" >> "$LOG_FILE" 2>&1
    fi
}

# Only run apt-get update if we need to install something
NEED_UPDATE=false
for cmd in firefox node npm python3 docker curl git; do
    if ! command -v "$cmd" &>/dev/null; then
        NEED_UPDATE=true
        break
    fi
done

if [ "$NEED_UPDATE" = true ]; then
    log "  Running apt-get update..."
    apt-get update >> "$LOG_FILE" 2>&1
fi

install_if_missing firefox firefox
install_if_missing node nodejs
install_if_missing npm npm
install_if_missing python3 python3

# Ensure pip packages for API
if ! python3 -c "import fastapi" 2>/dev/null; then
    log "  Installing Python packages (fastapi, uvicorn, pyyaml)..."
    pip3 install --break-system-packages fastapi uvicorn pyyaml >> "$LOG_FILE" 2>&1
fi

log "  Packages OK"

# ============================================================
# STEP 4: Build dashboard (if not built or source changed)
# ============================================================
log ""
log "[3/8] Building dashboard..."

if [ -d "$WEB_DIR" ]; then
    NEEDS_BUILD=false

    # Build if dist doesn't exist
    if [ ! -d "${WEB_DIR}/dist" ]; then
        NEEDS_BUILD=true
    fi

    # Build if source is newer than dist
    if [ -d "${WEB_DIR}/dist" ] && [ -f "${WEB_DIR}/src/App.tsx" ]; then
        if [ "${WEB_DIR}/src/App.tsx" -nt "${WEB_DIR}/dist/index.html" ] 2>/dev/null; then
            NEEDS_BUILD=true
        fi
    fi

    if [ "$NEEDS_BUILD" = true ]; then
        log "  Installing npm dependencies..."
        cd "$WEB_DIR"
        npm install >> "$LOG_FILE" 2>&1

        log "  Building dashboard..."
        npm run build >> "$LOG_FILE" 2>&1

        if [ -d "${WEB_DIR}/dist" ]; then
            log "  Dashboard built successfully"
        else
            log_error "  Dashboard build failed"
        fi
    else
        log "  Dashboard already built (up to date)"
    fi
else
    log "  Web directory not found — skipping dashboard build"
fi

# ============================================================
# STEP 5: Start Docker
# ============================================================
log ""
log "[4/8] Starting Docker..."
if command -v docker &>/dev/null; then
    if ! systemctl is-active --quiet docker; then
        systemctl start docker
        sleep 2
    fi
    if systemctl is-active --quiet docker; then
        log "  Docker is running"
    else
        log_error "  Docker failed to start"
    fi
else
    log "  Docker not installed — skipping"
fi

# ============================================================
# STEP 6: Start Docker Compose services (LiteLLM + OpenHands)
# ============================================================
log ""
log "[5/8] Starting Docker Compose services..."
if [ -f "${DOCKER_COMPOSE_DIR}/docker-compose.yml" ]; then
    if [ -f "${DOCKER_COMPOSE_DIR}/.env" ] && grep -q "DEEPSEEK_API_KEY=sk-" "${DOCKER_COMPOSE_DIR}/.env" 2>/dev/null; then
        cd "$DOCKER_COMPOSE_DIR"

        # Fix CRLF in .env if present
        sed -i 's/\r//' .env 2>/dev/null

        # Auto-allocate OpenHands port (avoid conflict with web app dev servers)
        OPENHANDS_PORT=$(find_free_port 3010 3099)
        export OPENHANDS_PORT
        log "  Allocated OpenHands port: $OPENHANDS_PORT"

        # Auto-generate OpenHands settings with actual API key
        LITELLM_KEY=$(grep LITELLM_MASTER_KEY .env | cut -d= -f2)
        if [ -n "$LITELLM_KEY" ]; then
            mkdir -p config
            cat > config/openhands_settings.json << EOFSET
{"language":"en","agent":"CodeActAgent","max_iterations":50,"confirmation_mode":false,"llm_model":"deepseek-v4-flash","llm_api_key":"${LITELLM_KEY}","llm_base_url":"http://litellm:4000","remote_runtime_resource_factor":1,"enable_default_condenser":true,"enable_sound_notifications":false,"user_consents_to_analytics":false}
EOFSET
            log "  OpenHands settings generated"
        fi

        docker compose up -d >> "$LOG_FILE" 2>&1

        # Wait for services
        wait_for_port $LITELLM_PORT "LiteLLM" 30 || true
        wait_for_port $OPENHANDS_PORT "OpenHands" 60 || true

        # Store allocated port for other scripts
        echo "$OPENHANDS_PORT" > "${WORKSTATION_DIR}/logs/openhands-port"
    else
        log "  Skipped — .env not configured (no API keys)"
        log "  To configure: edit ${DOCKER_COMPOSE_DIR}/.env"
    fi
else
    log "  Skipped — docker-compose.yml not found at ${DOCKER_COMPOSE_DIR}"
fi

# ============================================================
# STEP 7: Start Control Plane API
# ============================================================
log ""
log "[6/8] Starting Control Plane API..."
# Kill existing instance
pkill -f "uvicorn.*server" 2>/dev/null || true
pkill -f "python3.*server.py" 2>/dev/null || true
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

# ============================================================
# STEP 8: Verify xRDP + network policy
# ============================================================
log ""
log "[7/8] Verifying xRDP..."
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

log ""
log "[8/8] Verifying network access policy..."
if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
    TS_IP=$(tailscale ip -4 2>/dev/null | head -n1)
    log "  Tailscale active: ${TS_IP:-unknown-ip}"
else
    log_error "  Tailscale is not authenticated; admin access may depend on provider firewall break-glass rules"
fi
log "  No ufw/fail2ban changes are made by startup. Provider firewall + Tailscale ACLs/grants control ingress."

# ============================================================
# SUMMARY
# ============================================================
log ""
log "==== Startup Complete ===="
log ""
log "Services:"
log "  xRDP Desktop:     port 3389  (access through Tailscale/provider policy only)"
log "  Control Plane:    port $API_PORT  (use SSH forwarding or Tailscale/provider policy)"

if ss -tlnp | grep -q ":${LITELLM_PORT} "; then
    log "  LiteLLM:          port $LITELLM_PORT  (running; keep private)"
else
    log "  LiteLLM:          port $LITELLM_PORT  (not started — configure .env)"
fi

if ss -tlnp | grep -q ":${OPENHANDS_PORT} "; then
    log "  OpenHands:        port $OPENHANDS_PORT  (running; keep private)"
else
    log "  OpenHands:        port $OPENHANDS_PORT  (not started — configure .env)"
fi

if [ -d "${WEB_DIR}/dist" ]; then
    log "  Dashboard:        local port $API_PORT  (built)"
else
    log "  Dashboard:        NOT BUILT"
fi

log ""
log "Benchmark: $(python3 ${WORKSTATION_DIR}/bench-scripts/run-benchmark.py list 2>/dev/null | tail -1 || echo 'not available')"
log ""
log "Log file: $LOG_FILE"
