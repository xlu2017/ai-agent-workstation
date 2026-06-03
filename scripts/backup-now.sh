#!/usr/bin/env bash
# backup-now.sh — Create a BorgBackup archive of workstation data
set -euo pipefail

BACKUP_REPO="/opt/workstation/backups/main"
LOG_FILE="/opt/workstation/logs/backup.log"
ARCHIVE_NAME="auto-$(date +%Y%m%d-%H%M%S)"

echo "[$(date -Iseconds)] Starting backup: $ARCHIVE_NAME" | tee -a "$LOG_FILE"

# Create archive
borg create \
    --stats \
    --compression zstd,3 \
    "$BACKUP_REPO::$ARCHIVE_NAME" \
    /opt/workstation/repos \
    /opt/workstation/knowledge \
    /home/agent/ai-workstation/config \
    /home/agent/ai-workstation/docker-compose.yml \
    2>&1 | tee -a "$LOG_FILE"

# Prune old archives
borg prune \
    --keep-daily=7 \
    --keep-weekly=4 \
    --keep-monthly=6 \
    "$BACKUP_REPO" \
    2>&1 | tee -a "$LOG_FILE"

# Compact
borg compact "$BACKUP_REPO" 2>&1 | tee -a "$LOG_FILE"

echo "[$(date -Iseconds)] Backup complete: $ARCHIVE_NAME" | tee -a "$LOG_FILE"
