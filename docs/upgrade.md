# Upgrade Guide

## OpenHands Upgrade

```bash
cd ~/ai-workstation

# Pull latest image
docker compose pull openhands

# Restart with new image
docker compose up -d openhands

# Verify
docker compose ps
docker compose logs openhands --tail=20
```

**Rollback:**
```bash
# Find previous image
docker images ghcr.io/all-hands-ai/openhands --format "{{.Tag}} {{.CreatedAt}}"

# Pin to specific version in docker-compose.yml
# image: ghcr.io/all-hands-ai/openhands:0.30.0
docker compose up -d openhands
```

## LiteLLM Upgrade

```bash
cd ~/ai-workstation

# Pull latest
docker compose pull litellm

# Restart
docker compose up -d litellm

# Verify health
sleep 10
curl -s http://localhost:4000/health/liveliness
```

**Rollback:**
```bash
# Pin version in docker-compose.yml
# image: ghcr.io/berriai/litellm:main-v1.XX.XX
docker compose up -d litellm
```

## Node.js Upgrade

```bash
# Check current
node --version

# Update via NodeSource
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs

# Verify
node --version
npm --version
```

## System Packages

```bash
sudo apt update && sudo apt upgrade -y

# Reboot if kernel updated
sudo needrestart -r a
```

## Docker Engine Upgrade

```bash
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify
docker --version
docker compose version
```

## Chrome Upgrade

```bash
sudo apt update
sudo apt install --only-upgrade google-chrome-stable
google-chrome --version
```

## UV (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
uv --version
```

## Full Stack Upgrade Checklist

1. [ ] Backup first: `./scripts/backup-now.sh`
2. [ ] System packages: `sudo apt update && sudo apt upgrade -y`
3. [ ] Docker images: `docker compose pull`
4. [ ] Restart services: `docker compose up -d`
5. [ ] Verify health: `curl localhost:4000/health/liveliness`
6. [ ] Verify OpenHands: browse to localhost:3000
7. [ ] Test API call through LiteLLM
8. [ ] Check node exporter: `curl localhost:9100/metrics | head`
