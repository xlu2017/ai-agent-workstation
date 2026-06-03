# RFC-008: VM Snapshot Management

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Automated management of Hetzner Cloud snapshots for cost optimization, disaster recovery, and environment versioning.

## Motivation

Manual snapshot management is error-prone:
- Forgetting to snapshot before deletion wastes work
- Stale snapshots accumulate cost
- No versioning of environment states
- No automated pause/resume workflow

## Architecture

```
┌─────────────────────┐
│  Snapshot Manager   │  (cron + hcloud CLI)
│                     │
│  ┌───────────────┐  │
│  │ Auto-snapshot │  │  Daily/weekly
│  │ Auto-prune    │  │  Keep last N
│  │ Auto-pause    │  │  After idle timeout
│  │ Auto-resume   │  │  On SSH/API access
│  └───────────────┘  │
└──────────┬──────────┘
           │ hcloud API
           ▼
┌─────────────────────┐
│  Hetzner Cloud API  │
│  Snapshots, Servers │
└─────────────────────┘
```

## Features

### Auto-Snapshot
```bash
# Daily at 2 AM (before backup)
0 2 * * * hcloud server create-image --type snapshot \
  --description "auto-$(date +%Y%m%d)" <server-id>
```

### Auto-Prune
```bash
# Keep last 7 daily + 4 weekly + 3 monthly
# Delete older snapshots
./scripts/prune-snapshots.sh --keep-daily=7 --keep-weekly=4 --keep-monthly=3
```

### Auto-Pause (idle detection)
```bash
# If no SSH session and no Docker activity for 4 hours:
# 1. Create snapshot
# 2. Delete server
# 3. Send notification
```

### Auto-Resume
```bash
# Triggered by:
# - API call to webhook
# - Scheduled task (business hours)
# - Manual CLI command
./scripts/resume-workstation.sh
```

## Snapshot Naming Convention

```
workstation-auto-20260603          (daily auto)
workstation-weekly-20260603        (weekly)
workstation-before-upgrade-v2.1    (manual, before changes)
workstation-stable-20260601        (known-good state)
```

## Cost Management

| Snapshots Kept | Storage (30GB each) | Monthly Cost |
|----------------|--------------------:|-------------:|
| 7 daily | 210 GB | $2.52 |
| 4 weekly | 120 GB | $1.44 |
| 3 monthly | 90 GB | $1.08 |
| **Total** | **420 GB** | **$5.04** |

## Environment Versioning

Snapshots serve as versioned environments:
```
v1.0 — Base setup (Docker, tools)
v1.1 — + OpenHands + LiteLLM
v1.2 — + Chrome + knowledge system
v2.0 — Major upgrade (Node 24, Python 3.14)
```

Can roll back to any version by creating server from snapshot.

## Implementation

### Required: `hcloud` CLI

```bash
# Install
curl -sL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz | tar xz
sudo mv hcloud /usr/local/bin/

# Configure
hcloud context create workstation
# Enter API token from Hetzner Cloud Console
```

### Scripts

- `scripts/snapshot-create.sh` — Create named snapshot
- `scripts/snapshot-prune.sh` — Prune old snapshots
- `scripts/pause-workstation.sh` — Snapshot + delete
- `scripts/resume-workstation.sh` — Create from latest snapshot

## Security

- Hetzner API token stored in env var (not committed)
- Snapshots encrypted at rest by Hetzner
- Deletion requires API token (no accidental deletion)

## Open Questions

1. Notification mechanism for auto-pause? (Email, webhook, Slack?)
2. Should auto-resume support scheduled "business hours"?
3. Incremental snapshots (not supported by Hetzner — always full)?
4. Off-site backup of snapshots to Hetzner Object Storage?
