#!/usr/bin/env bash
# workstation-shutdown.sh — Graceful shutdown of AI Workstation services

set -euo pipefail

LOG_DIR="/opt/workstation/logs"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_DIR}/shutdown.log"; }

log "==== AI Workstation Shutdown ===="

# Stop Control Plane API
log "Stopping Control Plane API..."
pkill -f "uvicorn.*server" 2>/dev/null && log "  Stopped" || log "  Was not running"

# Stop Docker Compose
log "Stopping Docker services..."
if [ -f /home/agent/ai-workstation/docker-compose.yml ]; then
    cd /home/agent/ai-workstation
    docker compose down >> "${LOG_DIR}/shutdown.log" 2>&1 && log "  Stopped" || log "  Was not running"
fi

log "==== Shutdown Complete ===="
