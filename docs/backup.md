# Backup & Restore

## BorgBackup Configuration

**Repository:** `/opt/workstation/backups/main`
**Encryption:** None (server already encrypted at rest by Hetzner)

### What's backed up:
- `/opt/workstation/repos/` — All git repositories and worktrees
- `/opt/workstation/knowledge/` — Knowledge YAML files
- `/home/agent/ai-workstation/config/` — LiteLLM and service configs
- `/home/agent/ai-workstation/docker-compose.yml` — Service definitions

### What's NOT backed up:
- `.env` files (secrets — manage separately)
- Docker images (re-pullable)
- `/opt/workstation/backups/` (recursive backup)
- System packages (re-installable via setup.sh)

## Manual Backup

```bash
/opt/workstation/scripts/backup-now.sh
```

Or manually:
```bash
borg create \
  /opt/workstation/backups/main::manual-$(date +%Y%m%d-%H%M%S) \
  /opt/workstation/repos \
  /opt/workstation/knowledge \
  /home/agent/ai-workstation/config \
  /home/agent/ai-workstation/docker-compose.yml
```

## Automatic Backup (cron)

```bash
# Added by setup — runs daily at 3 AM
crontab -l | grep backup
# 0 3 * * * /opt/workstation/scripts/backup-now.sh >> /opt/workstation/logs/backup.log 2>&1
```

## Restore

### List available backups:
```bash
borg list /opt/workstation/backups/main
```

### Restore specific directory:
```bash
cd /
borg extract /opt/workstation/backups/main::ARCHIVE_NAME opt/workstation/repos/
```

### Restore everything:
```bash
cd /
borg extract /opt/workstation/backups/main::ARCHIVE_NAME
```

### Restore specific file:
```bash
borg extract /opt/workstation/backups/main::ARCHIVE_NAME opt/workstation/knowledge/react-patterns.yaml
```

## Pruning Old Backups

```bash
borg prune \
  --keep-daily=7 \
  --keep-weekly=4 \
  --keep-monthly=6 \
  /opt/workstation/backups/main

borg compact /opt/workstation/backups/main
```

## Pause/Resume (Cloud-specific)

### Pause (stop paying):
```bash
# 1. Run final backup
/opt/workstation/scripts/backup-now.sh

# 2. Create Hetzner snapshot (via web console or hcloud CLI)
hcloud server create-image --type snapshot --description "workstation-$(date +%Y%m%d)" <server-id>

# 3. Delete server
hcloud server delete <server-id>

# Cost while paused: ~$0.36/mo (snapshot) + $13.52/mo (volume, if kept)
```

### Resume:
```bash
# 1. Create new server from snapshot
hcloud server create --image <snapshot-id> --type ccx33 --location fsn1 --name workstation

# 2. Reattach volume (if used)
hcloud volume attach <volume-id> --server workstation

# 3. Start services
ssh agent@<new-ip> "cd ~/ai-workstation && docker compose up -d"
```

## Disaster Recovery

If the server is completely lost:

1. Provision new CCX33 from fresh Ubuntu 24.04
2. Run `setup.sh` (installs all tools)
3. Restore from off-site backup (if available) or re-clone repos
4. Copy `.env` file (from password manager)
5. `docker compose up -d`

Total recovery time: ~30 minutes.
