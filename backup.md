# Backup & Restore

Procedures for backing up, restoring, pausing, and resuming the workstation.

---

## Pause/Resume

The primary cost-saving mechanism: snapshot the server, delete it, and recreate from snapshot when needed.

### Pause (Stop Billing)

**Cost when paused:** ~$0.36/mo (30GB snapshot) vs $73.99/mo running

```bash
# 1. Stop services cleanly
cd ~/ai-workstation
docker compose down

# 2. Commit any uncommitted git work
cd ~/projects
for dir in */; do
    if [ -d "$dir/.git" ]; then
        echo "Checking $dir..."
        (cd "$dir" && git status --short)
    fi
done

# 3. Create snapshot via Hetzner Console:
#    https://console.hetzner.cloud → Select server → Snapshots → Create Snapshot
#    Or via CLI:
#    hcloud server create-image --type snapshot --description "workstation-$(date +%Y%m%d)" <server-id>

# 4. Once snapshot is confirmed, delete the server:
#    Hetzner Console → Select server → Delete
#    Or via CLI:
#    hcloud server delete <server-id>
```

### Resume (From Snapshot)

**Time to resume:** ~30 seconds

```bash
# Via Hetzner Console:
# 1. Go to: https://console.hetzner.cloud
# 2. Servers → Create Server
# 3. Image tab → Snapshots → Select your snapshot
# 4. Server type: CCX33 (or larger if needed)
# 5. Location: Same as before (or any)
# 6. SSH key: Select your key
# 7. Create

# Via CLI (hcloud):
hcloud server create \
  --name ai-workstation \
  --type ccx33 \
  --image <snapshot-id> \
  --ssh-key <key-name> \
  --location hel1

# After server is up:
ssh agent@<new-ip>
cd ~/ai-workstation
docker compose up -d

# Re-authenticate Tailscale (IP changed):
sudo tailscale up
```

**Note:** The server gets a new public IP after recreation. Tailscale handles this transparently — your Tailscale hostname stays the same.

---

## Daily Backups

### What to back up

| Data | Location | Method |
|------|----------|--------|
| Configuration | `~/ai-workstation/` | Git (committed) |
| API keys | `~/ai-workstation/.env` | Encrypted backup |
| Projects | `~/projects/` | Git remote (GitHub) |
| Docker volumes | `/var/lib/docker/volumes/` | Only if stateful |

### Automated backup script

```bash
#!/bin/bash
# ~/ai-workstation/scripts/backup.sh
# Run daily via cron: 0 3 * * * /home/agent/ai-workstation/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="/home/agent/ai-workstation/backups"
DATE=$(date +%Y%m%d-%H%M)
RETENTION_DAYS=7

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup..."

# Backup configuration (excluding secrets)
tar -czf "${BACKUP_DIR}/config-${DATE}.tar.gz" \
    -C /home/agent/ai-workstation \
    --exclude='.env' \
    --exclude='backups' \
    --exclude='logs' \
    config/ docker-compose.yml scripts/

# Backup .env encrypted (requires BACKUP_PASSPHRASE env var)
if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
    gpg --batch --yes --passphrase "${BACKUP_PASSPHRASE}" \
        --symmetric --cipher-algo AES256 \
        -o "${BACKUP_DIR}/env-${DATE}.gpg" \
        /home/agent/ai-workstation/.env
fi

# Verify all git repos are pushed
echo "Checking git repos..."
for dir in /home/agent/projects/*/; do
    if [ -d "$dir/.git" ]; then
        UNPUSHED=$(git -C "$dir" log --oneline @{u}..HEAD 2>/dev/null | wc -l)
        if [ "$UNPUSHED" -gt 0 ]; then
            echo "  WARNING: ${dir} has ${UNPUSHED} unpushed commits"
        fi
    fi
done

# Clean old backups
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "*.gpg" -mtime +${RETENTION_DAYS} -delete

echo "[$(date)] Backup complete: ${BACKUP_DIR}/config-${DATE}.tar.gz"
```

### Enable daily backup cron

```bash
chmod +x ~/ai-workstation/scripts/backup.sh
crontab -e
# Add: 0 3 * * * /home/agent/ai-workstation/scripts/backup.sh >> /home/agent/ai-workstation/logs/backup.log 2>&1
```

---

## Restore from Backup

### Full restore (new server)

```bash
# 1. Run setup.sh on fresh Ubuntu 24.04
sudo bash setup.sh

# 2. Restore configuration
cd ~/ai-workstation
tar -xzf backups/config-YYYYMMDD-HHMM.tar.gz

# 3. Restore .env
gpg --batch --passphrase "${BACKUP_PASSPHRASE}" \
    -d backups/env-YYYYMMDD-HHMM.gpg > .env
chmod 600 .env

# 4. Start services
./scripts/start-services.sh

# 5. Clone project repos
cd ~/projects
git clone https://github.com/user/repo1.git
git clone https://github.com/user/repo2.git
```

### Partial restore (config only)

```bash
cd ~/ai-workstation
docker compose down
tar -xzf backups/config-YYYYMMDD-HHMM.tar.gz
docker compose up -d
```

---

## Hetzner Snapshots

### Create snapshot (via CLI)

```bash
# Install hcloud CLI
# https://github.com/hetznercloud/cli/releases

# List servers
hcloud server list

# Create snapshot
hcloud server create-image --type snapshot \
    --description "workstation-$(date +%Y%m%d)" \
    <server-id>

# List snapshots
hcloud image list --type snapshot

# Delete old snapshot
hcloud image delete <snapshot-id>
```

### Snapshot pricing

- Storage: $0.012/GB/month
- Typical workstation snapshot (30–50 GB): $0.36–0.60/month
- Keep 1–2 snapshots max to minimize cost

---

## Disaster Recovery

### Scenario: Server completely lost (no snapshot)

**Recovery time:** ~2 hours

1. Create new CCX33 from stock Ubuntu 24.04 image
2. SSH in, clone this repo
3. Run `setup.sh`
4. Restore `.env` from encrypted backup (or re-enter API keys)
5. Run `start-services.sh`
6. Re-clone project repos from GitHub
7. Re-authenticate Tailscale

### Scenario: Snapshot exists but corrupted

1. Try creating from a different (older) snapshot
2. If no valid snapshot: follow "Server completely lost" procedure
3. Key insight: All valuable data is in Git. The server is reproducible.

### Scenario: API provider down

LiteLLM handles this automatically via fallback chain:
1. DeepSeek down → routes to Qwen
2. Qwen down → routes to Claude Haiku
3. All down → OpenHands shows error; wait and retry

No manual intervention needed for transient outages.

---

## Migration: Cloud → Dedicated

When you're ready to switch from CCX33 to AX42-U:

```bash
# On current cloud server:
# 1. Stop services
cd ~/ai-workstation && docker compose down

# 2. Create tarball of workstation
tar -czf /tmp/workstation-migration.tar.gz \
    -C /home/agent \
    ai-workstation/ projects/

# On new dedicated server (after setup.sh):
# 3. Transfer
scp cloud-server:/tmp/workstation-migration.tar.gz /tmp/

# 4. Extract
tar -xzf /tmp/workstation-migration.tar.gz -C /home/agent/
chown -R agent:agent /home/agent/ai-workstation /home/agent/projects

# 5. Start services
su - agent -c '/home/agent/ai-workstation/scripts/start-services.sh'

# 6. Update Tailscale
sudo tailscale up

# 7. Verify everything works, then delete cloud server
```

---

## Storage Management

### Check disk usage

```bash
# System overview
df -h /

# Detailed breakdown
ncdu /home/agent

# Docker usage
docker system df
```

### Add extra storage (Hetzner Cloud volumes)

```bash
# Via Console or CLI:
hcloud volume create --name data --size 100 --server <server-id>

# Mount (first time):
mkfs.ext4 /dev/disk/by-id/scsi-0HC_Volume_<id>
mkdir -p /mnt/data
mount /dev/disk/by-id/scsi-0HC_Volume_<id> /mnt/data

# Add to /etc/fstab for persistence:
echo '/dev/disk/by-id/scsi-0HC_Volume_<id> /mnt/data ext4 discard,nofail,defaults 0 0' >> /etc/fstab

# Volume pricing: $0.048/GB/month (100GB = $4.80/mo)
```
