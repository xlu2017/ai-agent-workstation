# Deployment Log

Complete record of the initial workstation deployment performed on 2026-06-03.

---

## Server Provisioned

| Field | Value |
|-------|-------|
| Provider | Hetzner Cloud |
| Plan | CCX33 (Dedicated vCPU) |
| vCPUs | 8 (AMD, dedicated) |
| RAM | 32 GB |
| Storage | 240 GB NVMe SSD |
| Traffic | 30 TB/month |
| Location | Falkenstein, Germany (eu-central) |
| Server Name | `<hostname>` |
| Public IPv4 | `<server-ip>` |
| OS | Ubuntu 24.04 LTS |
| Billing | Hourly ($0.119/hr, capped at $73.99/mo + $0.60/mo IPv4) |
| Created | 2026-06-03 |

---

## SSH Access

| Field | Value |
|-------|-------|
| Private Key | `~/.ssh/hetzner_workstation` (Ed25519) |
| Public Key | `ssh-ed25519 <ssh-key> ai-workstation` |
| SSH User | `agent` (non-root, has sudo) |
| Root Login | Disabled (SSH hardened) |
| Connect | `ssh -i ~/.ssh/hetzner_workstation agent@<server-ip>` |

---

## Setup Execution

`setup.sh` was run as root and completed all 10 steps:

1. System update (DEBIAN_FRONTEND=noninteractive)
2. Created `agent` user with sudo privileges
3. Installed core packages: chromium, xfce4, xrdp, build-essential, tmux, git, curl, htop, ncdu, jq, unzip
4. Installed Docker CE + Docker Compose plugin
5. Installed Node.js 20 (via NodeSource)
6. Installed Tailscale
7. Configured UFW firewall (SSH + Tailscale allowed)
8. SSH hardening (disabled root login, disabled password auth, enabled fail2ban)
9. Configured xRDP (port 3389, xfce4 session)
10. Created workstation directory (`/home/agent/ai-workstation/`) with docker-compose.yml and .env

**Result:** All 10 steps completed successfully. Exit code 0.

---

## Services Deployed

### LiteLLM Proxy (port 4000)

- **Image:** `ghcr.io/berriai/litellm:main-latest`
- **Status:** Running, healthy
- **Healthcheck:** Python urllib → `http://localhost:4000/health/liveliness`
- **Auth:** Bearer token via `LITELLM_MASTER_KEY` env var
- **Models configured:**
  - `deepseek-v4-flash` (primary) — DeepSeek API
  - `deepseek-v4-pro` (complex reasoning) — DeepSeek API
  - `qwen-turbo` (secondary fallback) — DashScope (not configured yet)
  - `claude-haiku` (premium fallback) — Anthropic (not configured yet)
  - `gpt-4.1-mini` — OpenAI (not configured yet)
  - `gemini-flash` — Google (not configured yet)
- **Fallback routing:** deepseek-v4-flash → qwen-turbo → claude-haiku

### OpenHands (port 3000)

- **Image:** `ghcr.io/all-hands-ai/openhands:latest`
- **Status:** Running
- **Configuration via UI:**
  - Custom Model: `openai/deepseek-v4-flash`
  - Base URL: `http://litellm:4000`
  - API Key: LiteLLM master key
  - Agent: CodeActAgent
- **Depends on:** LiteLLM being healthy

---

## API Keys Configured

| Provider | Status | Key Name |
|----------|--------|----------|
| DeepSeek | Active (topped up) | `ai-workstation` |
| DashScope/Qwen | Skipped | — |
| Anthropic | Not configured | — |
| OpenAI | Not configured | — |
| Google Gemini | Not configured | — |

---

## End-to-End Verification

### Direct DeepSeek API Test

```
POST https://api.deepseek.com/v1/chat/completions
Model: deepseek-chat
Response: "Hello"
Status: SUCCESS
```

### LiteLLM Proxy Test

```
POST http://localhost:4000/v1/chat/completions
Authorization: Bearer <LITELLM_MASTER_KEY>
Model: deepseek-v4-flash
Response: reasoning_content="We need to respond with a single word greeting."
Status: SUCCESS
```

---

## Remote Desktop Access

- **Protocol:** RDP via xRDP
- **Port:** 3389
- **Desktop:** XFCE 4
- **User:** `agent`
- **Status:** Verified working via xfreerdp
- **Security:** Port 3389 currently open (close after Tailscale setup)

---

## Known Issues & Fixes Applied

### 1. LiteLLM healthcheck fails (curl not in container)

**Problem:** The LiteLLM Docker image doesn't include `curl`.  
**Fix:** Changed healthcheck to use Python's `urllib.request`:
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:4000/health/liveliness')"]
```

### 2. LiteLLM requires PostgreSQL when master_key is in config file

**Problem:** Setting `master_key` in `litellm_config.yaml` triggers LiteLLM's Prisma ORM which requires PostgreSQL.  
**Fix:** Removed `master_key` from config file. LiteLLM picks it up from the `LITELLM_MASTER_KEY` environment variable (passed via docker-compose.yml) instead.

### 3. Private repo couldn't be cloned on server

**Problem:** `git clone` failed (no GitHub auth on server).  
**Fix:** Used `scp` to copy repo files directly from Devin's VM to the server.

---

## Remaining Steps (Post-Deployment)

1. **Set up Tailscale** — `sudo tailscale up` (requires browser auth)
2. **Close port 3389** after Tailscale is working — `sudo ufw delete allow 3389/tcp`
3. **Optional:** Add DashScope, Anthropic, OpenAI, Gemini keys to `.env` for fallback models
4. **Optional:** Set up Caddy reverse proxy for HTTPS (if using a domain)
5. **Optional:** Configure git worktrees for parallel agent workspaces

---

## File Locations on Server

```
/home/agent/ai-workstation/
├── docker-compose.yml          # Service definitions (running)
├── .env                        # API keys (DEEPSEEK + LITELLM_MASTER_KEY set)
├── config/
│   └── litellm_config.yaml     # Model routing (master_key removed from here)
├── scripts/
│   └── start-services.sh       # Startup script with health checks
└── logs/                       # Service logs directory

/home/agent/projects/           # Workspace for OpenHands agent sandboxes
```

---

## Cost Summary

| Item | Monthly Cost |
|------|-------------|
| Hetzner Cloud CCX33 | $73.99 |
| IPv4 address | $0.60 |
| DeepSeek API (estimated moderate use) | $5–20 |
| **Total (running)** | **$80–95** |
| **Paused (snapshot only)** | **$0.36** |
