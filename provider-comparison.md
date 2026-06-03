# Provider Comparison

## Infrastructure Providers

### 1. Hetzner Cloud (General Purpose / Dedicated vCPU)

| Plan | vCPU | RAM | SSD | Monthly | Hourly |
|------|------|-----|-----|---------|--------|
| CCX13 | 2 (AMD dedicated) | 8 GB | 80 GB | $18.49 | $0.0296 |
| CCX23 | 4 (AMD dedicated) | 16 GB | 160 GB | $36.99 | $0.0593 |
| CCX33 | 8 (AMD dedicated) | 32 GB | 240 GB | $73.99 | $0.1186 |
| CCX43 | 16 (AMD dedicated) | 64 GB | 480 GB | $147.49 | $0.2364 |

**Shared vCPU (Regular Performance):**

| Plan | vCPU | RAM | SSD | Monthly |
|------|------|-----|-----|---------|
| CPX32 | 4 (AMD shared) | 8 GB | 160 GB | $15.99 |
| CPX42 | 8 (AMD shared) | 16 GB | 240 GB | $29.99 |
| CPX52 | 16 (AMD shared) | 32 GB | 360 GB | $42.99 |

- **Snapshot pricing:** $0.012/GB/month
- **Traffic included:** 20 TB (US), 1–20 TB (EU depending on plan)
- **Stopped instances still bill:** Yes — must delete to stop billing
- **IPv4:** Included
- **Locations:** Germany (FSN1, NBG1), Finland (HEL1), USA (HIL, ASH), Singapore
- **Ubuntu 24.04:** Supported
- **Docker support:** Excellent (one-click app available)
- **API quality:** Excellent (Terraform provider, CLI, REST API)
- **Documentation:** Very good, community-focused
- **Operational risks:** EU company, GDPR-compliant; US locations available but newer

**Source:** https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/

---

### 2. Hetzner Dedicated Servers (AX Line)

| Plan | CPU | Cores/Threads | RAM | Storage | Monthly | Setup Fee |
|------|-----|---------------|-----|---------|---------|-----------|
| AX41-NVMe | Ryzen 5 3600 (Zen 2) | 6c/12t | 64 GB DDR4 | 2×512 GB NVMe | ~$42 | ~$43 |
| AX42-U | Ryzen 7 PRO 8700GE (Zen 4) | 8c/16t | 64 GB DDR5 | 2×512 GB NVMe | ~$59 | ~$255 |
| AX102-U | Ryzen 9 7950X3D (Zen 4) | 16c/32t | 128 GB DDR5 | 2×1.92 TB NVMe | ~$113–126 | ~$292 |

- **Traffic:** Unlimited at 1 Gbit/s
- **Stopped instances still bill:** Yes (dedicated hardware reserved)
- **Ubuntu 24.04:** Supported
- **Docker support:** Full bare-metal, excellent
- **Remote desktop:** Full control (VNC rescue, KVM console)
- **Delivery time:** 1–7 days (not instant)
- **API quality:** Robot API for management, not as modern as Cloud API
- **Documentation:** Good
- **Operational risks:** Hardware failures require ticket; no live migration. Setup fee is non-refundable.

**Note:** EUR prices converted at ~1.09 USD/EUR. Hetzner shows EUR on order page; actual USD charges may vary with FX.

**Source:** https://www.hetzner.com/dedicated-rootserver/ax102/, https://robot.hetzner.com/order/index/country/US

---

### 3. OVHcloud

**VPS (2026 range):**

| Plan | vCores | RAM | SSD | Monthly |
|------|--------|-----|-----|---------|
| VPS-1 | 4 | 8 GB | 75 GB | $6.46 |
| VPS-2 | 6 | 12 GB | 100 GB NVMe | $9.99 |
| VPS-3 | 8 | 24 GB | 200 GB NVMe | $19.97 |

**Rise Dedicated:**

| Plan | CPU | Cores/Threads | RAM | Storage | Monthly | Setup Fee |
|------|-----|---------------|-----|---------|---------|-----------|
| RISE-1 | Intel Xeon-E 2386G | 6c/12t | 32–128 GB | 2×512 GB | $70 | $70 |
| RISE-2 | Intel Xeon-E 2388G | 8c/16t | 32–128 GB | 2×512 GB | ~$85 | $85 |

**Advance Dedicated:**

| Plan | CPU | RAM | Monthly | Setup Fee |
|------|-----|-----|---------|-----------|
| Advance-1 | AMD EPYC 4244P (6c/12t) | 32–192 GB | $115 | $115 (free promo) |

- **Traffic:** Unlimited (500 Mbps Rise, 1–5 Gbps Advance)
- **Stopped instances still bill:** Dedicated = yes; VPS = yes
- **Ubuntu 24.04:** Supported
- **Docker support:** Good
- **Remote desktop:** IPMI/KVM on dedicated
- **API quality:** Moderate (OVH API is functional but less ergonomic)
- **Documentation:** Adequate, sometimes inconsistent between regions
- **Operational risks:** Support quality varies by region; hardware provisioning can be slow

**Source:** https://www.ovhcloud.com/en/vps/, https://eco.us.ovhcloud.com/rise/

---

### 4. DigitalOcean

| Plan | vCPU | RAM | SSD | Transfer | Monthly |
|------|------|-----|-----|----------|---------|
| Basic 4vCPU | 4 (shared) | 8 GB | 160 GB | 5 TB | $48 |
| Basic 8vCPU | 8 (shared) | 16 GB | 320 GB | 6 TB | $96 |
| Premium AMD 4vCPU | 4 (shared) | 8 GB | 100 GB NVMe | 5 TB | $56 |
| CPU-Optimized 8vCPU | 8 (dedicated) | 16 GB | — | 6 TB | $192 |

- **Snapshot pricing:** $0.06/GB/month
- **Stopped instances still bill:** Yes (must destroy to stop)
- **Ubuntu 24.04:** Supported
- **Docker support:** Good (1-click apps)
- **API quality:** Excellent (well-documented REST API, Terraform provider)
- **Documentation:** Excellent (community tutorials)
- **Operational risks:** Higher per-unit cost; no bare-metal option

**Source:** https://www.digitalocean.com/pricing/droplets

---

### 5. AWS EC2

| Instance | vCPU | RAM | Hourly | Monthly (730h) |
|----------|------|-----|--------|----------------|
| t3.xlarge | 4 | 16 GB | $0.208 | $151.84 |
| m6i.xlarge | 4 | 16 GB | $0.240 | $175.20 |
| m6i.2xlarge | 8 | 32 GB | $0.480 | $350.40 |
| c7i.xlarge | 4 | 8 GB | $0.223 | $162.88 |

- **Storage:** EBS gp3 $0.08/GB/mo (100 GB = $8/mo extra)
- **Stopped instances:** EBS still bills; compute does NOT bill when stopped
- **Ubuntu 24.04:** Supported (official AMI)
- **Docker support:** Excellent
- **Remote desktop:** Via RDP/VNC (self-managed)
- **API quality:** Industry-leading
- **Documentation:** Best-in-class
- **Operational risks:** Complex billing; easy to overspend; egress charges ($0.09/GB after 100 GB/mo free)

**Source:** https://aws.amazon.com/ec2/pricing/on-demand/

---

### 6. RunPod

| GPU | VRAM | RAM | vCPUs | Hourly (Community) |
|-----|------|-----|-------|-------------------|
| RTX A5000 | 24 GB | 25 GB | 9 | $0.27 |
| L4 | 24 GB | 50 GB | 12 | $0.39 |
| RTX 4090 | 24 GB | 41 GB | 6 | $0.69 |
| A100 PCIe 80GB | 80 GB | 117 GB | 8 | $1.39 |
| H100 SXM | 80 GB | 125 GB | 20 | $3.29 |

- **Per-second billing**
- **Stopped instances:** Storage still bills ($0.10/GB/mo network volume, $0.07/GB/mo for container)
- **CPU-only workstation:** Not available — GPU-focused platform
- **Docker support:** Native (pods are Docker containers)
- **Ubuntu 24.04:** Via custom Docker image
- **Operational risks:** Community cloud = shared hardware, potential preemption; not designed for persistent dev workstations
- **Best use:** Burst GPU for ML training/inference

**Source:** https://www.runpod.io/pricing

---

### 7. Vast.ai

- **Marketplace model:** Prices set by supply/demand across 40+ data centers
- **Typical RTX 3090:** $0.15–0.30/hr
- **Typical A100 80GB:** $0.80–1.20/hr
- **Per-second billing**
- **Instance types:** On-demand (guaranteed), Interruptible (cheapest), Reserved (discounted)
- **Ubuntu 24.04:** Via custom Docker images
- **Docker support:** Native
- **Operational risks:** No SLA; host reliability varies; interruptible instances can be reclaimed; marketplace quality inconsistent
- **Best use:** Burst GPU at lowest cost for fault-tolerant workloads

**Source:** https://vast.ai/pricing, https://docs.vast.ai/guides/instances/pricing

---

## Model/API Providers

### 1. DeepSeek Official API

| Model | Context | Input (cache miss) | Input (cache hit) | Output |
|-------|---------|-------------------|-------------------|--------|
| deepseek-v4-flash | 1M | $0.14 | $0.0028 | $0.28 |
| deepseek-v4-pro | 1M | $0.435 | $0.003625 | $0.87 |
| deepseek-chat (legacy, V3) | 64K | $0.27 | $0.07 | $1.10 |
| deepseek-reasoner (legacy, R1) | 64K | $0.55 | $0.14 | $2.19 |

- **Availability:** Generally reliable; occasional congestion during peak hours
- **Rate limits:** 2500 concurrent (V4-Flash), 500 concurrent (V4-Pro)
- **Documentation:** Good (OpenAI-compatible format)
- **Operational risks:** China-based company; potential geopolitical/regulatory risk; occasional service degradation during high demand
- **Why select:** Extremely cost-effective; V4-Flash is 10-50× cheaper than Western alternatives for comparable quality

**Source:** https://api-docs.deepseek.com/quick_start/pricing

---

### 2. Alibaba DashScope / Qwen (International)

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| qwen3-max | $1.60 | $6.40 | Flagship; thinking mode supported |
| qwen-turbo-latest | $0.05 | $0.50 | Fast, cheap |
| qwen-max-latest | $1.60 | $6.40 | Non-thinking only |

- **Deployment:** International (Singapore endpoint) or Global (US Virginia / Germany Frankfurt)
- **Free quota:** 1M tokens (90-day validity) on activation
- **Documentation:** Good (English docs available)
- **API format:** DashScope SDK or OpenAI-compatible
- **Operational risks:** Alibaba Cloud dependency; international endpoint may have higher latency; less community adoption outside China
- **Why select:** Strong multilingual model; good fallback to DeepSeek; competitive pricing on turbo tier

**Source:** https://www.alibabacloud.com/help/en/model-studio/model-pricing

---

### 3. SiliconFlow

| Model | Context | Input | Output |
|-------|---------|-------|--------|
| DeepSeek-V4-Flash | 1049K | $0.14 | $0.28 |
| DeepSeek-V4-Pro | 1049K | $1.74 | $3.48 |
| Qwen3.6-27B | 262K | $0.30 | $3.20 |
| Qwen3.5-9B | 262K | $0.10 | $0.15 |
| Qwen3.5-122B-A10B | 262K | $0.26 | $2.08 |

- **$1 free credit on signup**
- **200+ models available**
- **API format:** OpenAI-compatible
- **Documentation:** Good
- **Operational risks:** Smaller company; less established SLA history; China-based infrastructure
- **Why select:** Unified API for multiple models (DeepSeek + Qwen + others); competitive pricing; good as secondary/fallback router

**Source:** https://www.siliconflow.com/pricing

---

### 4. OpenRouter

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| DeepSeek V3 | $0.20–0.27 | $0.77–1.14 | Routes to cheapest provider |
| Claude Sonnet 4.5 | $3.00 | $15.00 | Same as Anthropic direct |
| GPT-4o | $2.50 | $10.00 | Same as OpenAI direct |

- **Adds ~10–20% markup** over direct provider pricing for most models
- **Multi-provider routing** with automatic fallback
- **API format:** OpenAI-compatible
- **Documentation:** Good
- **Operational risks:** Dependency on upstream providers; markup increases cost; potential latency from routing layer
- **Why select:** Single API for all providers; useful as emergency fallback; not recommended as primary due to markup

**Source:** https://openrouter.ai/deepseek/deepseek-chat-v3-0324

---

### 5. Anthropic Claude

| Model | Input | Output |
|-------|-------|--------|
| Claude Opus 4.5+ | $5.00 | $25.00 |
| Claude Sonnet 4.5+ | $3.00 | $15.00 |
| Claude Haiku 4.5 | $1.00 | $5.00 |

- **Context:** 200K tokens
- **Cache hits:** 90% discount on input (5-min cache)
- **Rate limits:** Tier-based (starts at $5/mo spend)
- **Documentation:** Excellent
- **Operational risks:** Expensive for high-volume agentic use; rate limits can throttle heavy agent workloads
- **Why select:** Best-in-class code quality; excellent for complex reasoning; use as premium fallback only

**Source:** https://platform.claude.com/docs/en/about-claude/pricing

---

### 6. OpenAI

| Model | Input | Cached Input | Output |
|-------|-------|--------------|--------|
| GPT-4o | $2.50 | $1.25 | $10.00 |
| GPT-4.1 | $2.00 | $0.50 | $8.00 |
| GPT-4.1-mini | $0.40 | $0.10 | $1.60 |
| GPT-4.1-nano | $0.10 | $0.025 | $0.40 |

- **Context:** 128K (GPT-4o), 272K+ (newer models)
- **Documentation:** Excellent
- **Operational risks:** Most expensive tier; aggressive rate limits on lower tiers
- **Why select:** Broadest ecosystem support; best tool-calling reliability; use as fallback only

**Source:** https://developers.openai.com/api/docs/pricing

---

### 7. Google Gemini

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| Gemini 3.5 Flash | $1.50 | $9.00 | Includes thinking tokens |
| Gemini 2.5 Pro | $1.25–2.50 | $10.00–20.00 | GA pricing |
| Gemini 2.5 Flash | $0.15 | $0.60 | Budget option |
| Gemini 2.5 Flash-Lite | ~$0.075 | ~$0.30 | Cheapest (preview) |

- **Free tier:** Available with rate limits
- **Context:** Up to 1M tokens (2.5 Pro)
- **Documentation:** Good (Google AI Studio)
- **Operational risks:** Pricing changes frequently; model availability varies; thinking token costs can be unpredictable
- **Why select:** Very long context; generous free tier for testing; Flash-Lite is extremely cheap

**Source:** https://ai.google.dev/gemini-api/docs/pricing

---

## Summary Comparison Matrix

| Provider | Best For | Monthly Cost (target config) | Persistent? | Docker | Remote Desktop | Risk Level |
|----------|----------|------------------------------|-------------|--------|----------------|------------|
| Hetzner Dedicated AX42-U | **Primary workstation** | ~$59 | Yes | Excellent | VNC/SSH | Low |
| Hetzner Cloud CCX33 | Cloud workstation | $73.99 | Yes | Excellent | VNC/SSH | Low |
| OVHcloud Rise-1 | Budget dedicated | $70 | Yes | Good | IPMI | Medium |
| DigitalOcean 8vCPU | Managed cloud | $96 | Yes | Good | Console | Low |
| AWS EC2 m6i.xlarge | Enterprise cloud | $175+ | Partial | Excellent | Self-managed | Low |
| RunPod | Burst GPU only | $0.27–3.29/hr | No | Native | N/A | Medium |
| Vast.ai | Cheapest GPU burst | $0.15–1.20/hr | No | Native | N/A | High |

| API Provider | Best For | Cost (1M tokens in/out) | Reliability | Code Quality |
|-------------|----------|------------------------|-------------|--------------|
| DeepSeek V4-Flash | **Primary model** | $0.14/$0.28 | Good | Very Good |
| DeepSeek V4-Pro | Complex reasoning | $0.435/$0.87 | Good | Excellent |
| Qwen (DashScope) | Secondary/fallback | $0.05–1.60/$0.50–6.40 | Good | Good |
| SiliconFlow | Unified multi-model | Same as direct | Good | Good |
| Claude Sonnet 4.5 | Premium fallback | $3/$15 | Excellent | Best |
| OpenAI GPT-4.1-mini | Tool-calling fallback | $0.40/$1.60 | Excellent | Very Good |
| Gemini 2.5 Flash | Long-context tasks | $0.15/$0.60 | Good | Good |
