# Recommended Architecture

## Overview

A persistent Ubuntu 24.04 LTS cloud workstation (Hetzner Cloud CCX33) running self-hosted OpenHands behind LiteLLM Proxy, with DeepSeek as primary model provider and Qwen as secondary. Multiple agent sessions via git worktrees and tmux. Designed to be portable to Hetzner Dedicated hardware when always-on use is confirmed. Future-ready for GPU burst workers and UI bridge.

---

## Infrastructure Recommendation

### Primary: Hetzner Cloud CCX33

| Spec | Value |
|------|-------|
| CPU | 8 dedicated AMD vCPUs (EPYC) |
| RAM | 32 GB |
| Storage | 240 GB NVMe SSD (expandable via volumes) |
| Network | 1 Gbit/s, 20 TB included traffic |
| Location | Ashburn (US), Helsinki (EU), or Falkenstein (EU) |
| Monthly | $73.99 |
| Setup fee | None |
| Provisioning | Instant (~30 seconds) |

**Why CCX33 as primary:**

| Advantage | Detail |
|-----------|--------|
| Pause/resume | Delete server + keep snapshot ($0.012/GB/mo). Resume in 30s, no setup fee. |
| Instant provisioning | Available in seconds vs 1–5 days for dedicated |
| Easy scaling | Resize to CCX43 (16 vCPU/64GB) or CCX53 with one click |
| Snapshots | Native snapshot support for backup/migration |
| No upfront cost | No setup fee; pay only for time used |
| Portable | All config in setup.sh + docker-compose.yml — works identically on dedicated |

### Future upgrade path: Hetzner Dedicated AX42-U

When you confirm always-on usage (running 24/7 for months), migrate to dedicated:

| Spec | Value |
|------|-------|
| CPU | AMD Ryzen 7 PRO 8700GE (8c/16t, Zen 4) |
| RAM | 64 GB DDR5 |
| Storage | 2×512 GB NVMe (RAID 1) |
| Network | 1 Gbit/s, unlimited traffic |
| Monthly | ~$59 (saves $15/mo vs cloud) |
| Setup fee | ~$255 (one-time) |

Migration process: snapshot cloud → rsync to dedicated → switch DNS/Tailscale. All software is infrastructure-agnostic.

---

## Software Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Hetzner Cloud CCX33 (or Dedicated)              │
│                   Ubuntu 24.04 LTS                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │   OpenHands  │   │   LiteLLM    │   │   Caddy      │   │
│  │   (Docker)   │   │   Proxy      │   │   Reverse    │   │
│  │              │   │   (Docker)   │   │   Proxy      │   │
│  │  Port 3000   │   │  Port 4000   │   │  Port 443    │   │
│  └──────┬───────┘   └──────┬───────┘   └──────────────┘   │
│         │                   │                               │
│         │    ┌──────────────┴──────────────┐               │
│         │    │       Model Routing          │               │
│         │    ├──────────────────────────────┤               │
│         │    │ Primary: DeepSeek V4-Flash   │               │
│         │    │ Complex: DeepSeek V4-Pro     │               │
│         │    │ Fallback: Qwen-turbo         │               │
│         │    │ Emergency: Claude / OpenAI   │               │
│         │    └──────────────────────────────┘               │
│         │                                                   │
│  ┌──────┴───────────────────────────────────────────────┐  │
│  │              Docker Engine                             │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │  │
│  │  │ Agent 1 │ │ Agent 2 │ │ Agent 3 │ │ Browser │   │  │
│  │  │Sandbox  │ │Sandbox  │ │Sandbox  │ │Container│   │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Host Services                            │  │
│  │  • tmux session manager                              │  │
│  │  • Git worktrees (per-agent workspaces)             │  │
│  │  • xrdp / noVNC (remote desktop)                    │  │
│  │  • Chromium (headless + GUI)                        │  │
│  │  • Tailscale (secure remote access)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. OpenHands (Self-Hosted)

- **Role:** AI coding agent runtime
- **Deployment:** Docker container via `docker-compose`
- **Requirements:** Docker socket access, 4+ GB RAM, access to LiteLLM endpoint
- **Configuration:** Points to LiteLLM proxy at `http://localhost:4000`
- **Multi-session:** Each session spawns its own sandbox container
- **Source:** https://docs.openhands.dev/openhands/usage/run-openhands/local-setup

### 2. LiteLLM Proxy

- **Role:** Unified API gateway for all model providers
- **Deployment:** Docker container
- **Features:**
  - OpenAI-compatible API endpoint
  - Model routing (primary → fallback chain)
  - Rate limiting per model
  - Cost tracking and logging
  - API key management (single key for all backends)
  - Load balancing across providers
- **Configuration:** YAML config defining model→provider mappings
- **Port:** 4000 (internal)

### 3. Caddy Reverse Proxy

- **Role:** HTTPS termination, authentication, routing
- **Features:**
  - Automatic Let's Encrypt certificates
  - Basic auth or Tailscale auth for access control
  - Routes: `/` → OpenHands UI, `/litellm` → LiteLLM admin
- **Alternative:** Use Tailscale only (no public exposure needed)

### 4. Remote Access

- **Primary:** Tailscale (WireGuard mesh VPN)
  - Zero-config, no port exposure
  - MagicDNS for hostname access
  - Free for personal use (up to 100 devices)
- **Secondary:** xrdp + noVNC for full desktop when needed
- **SSH:** Standard SSH with key auth (port 22)

### 5. Session Management

- **tmux:** Named sessions per project/agent
- **Git worktrees:** Each agent session gets its own worktree from the same repo
  - Eliminates branch switching conflicts
  - Shared object store (disk-efficient)
  - Example: `git worktree add ../project-agent1 feature-branch`

### 6. Browser

- **Chromium:** Installed on host for agent browser actions
- **Headless mode:** For automated testing
- **noVNC:** For visual inspection when needed
- **Playwright:** For scripted browser automation

---

## Model Routing Strategy

```yaml
# LiteLLM config.yaml
model_list:
  - model_name: "default"          # OpenHands default model
    litellm_params:
      model: "deepseek/deepseek-v4-flash"
      api_base: "https://api.deepseek.com"
      api_key: "${DEEPSEEK_API_KEY}"

  - model_name: "reasoning"        # Complex tasks
    litellm_params:
      model: "deepseek/deepseek-v4-pro"
      api_base: "https://api.deepseek.com"
      api_key: "${DEEPSEEK_API_KEY}"

  - model_name: "fallback"         # When DeepSeek is down
    litellm_params:
      model: "qwen-turbo-latest"
      api_base: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
      api_key: "${DASHSCOPE_API_KEY}"

  - model_name: "premium"          # Emergency only
    litellm_params:
      model: "claude-haiku-4.5"
      api_key: "${ANTHROPIC_API_KEY}"

router_settings:
  routing_strategy: "simple-shuffle"  # or "latency-based-routing"
  num_retries: 3
  fallbacks:
    - default: ["fallback", "premium"]
    - reasoning: ["default", "premium"]
```

---

## Multi-Agent Session Architecture

```
Repository: /home/agent/projects/my-repo (bare clone)
├── worktree-main/          (git worktree for main branch)
├── worktree-feature-a/     (agent 1 working on feature A)
├── worktree-feature-b/     (agent 2 working on feature B)
└── worktree-bugfix-c/      (agent 3 working on bugfix C)

tmux sessions:
├── agent-1  (OpenHands session → worktree-feature-a)
├── agent-2  (OpenHands session → worktree-feature-b)
├── agent-3  (OpenHands session → worktree-bugfix-c)
├── monitor  (htop, docker stats, litellm logs)
└── dev      (manual development)
```

---

## Future Extensibility

### GPU Burst Workers (Phase 2)

When ML training or large model inference is needed:

1. **RunPod on-demand:** Spin up RTX 4090 ($0.69/hr) or A100 ($1.39/hr) for training jobs
2. **Vast.ai interruptible:** Cheapest option for fault-tolerant batch processing
3. **Integration:** SSH tunnel from Hetzner → RunPod; or use RunPod Serverless API

### Source-Aware UI Bridge (Phase 3)

Future component that routes tasks to appropriate agent based on:
- File type (frontend → browser-aware agent, backend → CLI agent)
- Complexity (simple → V4-Flash, complex → V4-Pro)
- Project context (worktree isolation)

### Scaling Up (Phase 4)

If workload exceeds AX42-U capacity:
- **Vertical:** Upgrade to AX102-U (16c/128GB, ~$113/mo) — requires migration
- **Horizontal:** Add Hetzner Cloud instances for parallel agent sandboxes
- **Hybrid:** Keep AX42-U as orchestrator, delegate heavy sandboxes to cloud

---

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Network access | Tailscale (no public ports except 443 if needed) |
| SSH | Key-only auth, fail2ban |
| Docker | Rootless mode where possible; sandbox isolation |
| Secrets | Environment variables via `.env` (not in git); Docker secrets |
| API keys | Stored in LiteLLM config, never exposed to agent sandboxes |
| Updates | Unattended-upgrades for security patches |
| Firewall | UFW: deny all inbound except Tailscale, SSH |

---

## Monitoring & Observability

| What | How |
|------|-----|
| Server health | `htop`, `netdata` (lightweight) |
| Docker containers | `docker stats`, Portainer (optional) |
| API costs | LiteLLM built-in cost tracking |
| Agent sessions | OpenHands session logs |
| Disk usage | `ncdu`, cron alerts at 80% |
| Uptime | Simple healthcheck script + email alert |
