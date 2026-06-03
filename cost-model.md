# Cost Model

## Budget Target: Under $200/month all-in

This document models the total monthly cost for the recommended configuration.

---

## Recommended Configuration

**Infrastructure:** Hetzner Dedicated AX42-U  
**Primary model:** DeepSeek V4-Flash (direct API)  
**Secondary model:** Qwen via DashScope or SiliconFlow  
**Fallback models:** Claude Haiku 4.5, GPT-4.1-mini (emergency only)

---

## Infrastructure Costs

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Hetzner AX42-U server | $59.00 | 8c/16t Zen4, 64GB DDR5, 2×512GB NVMe |
| IPv4 address | Included | 1 dedicated IPv4 |
| Traffic | Included | Unlimited at 1 Gbit/s |
| Backup storage (optional) | $0–5.00 | Hetzner Storage Box BX11: 1TB for ~$4.18/mo |
| Domain (optional) | $0–1.50 | If needed for HTTPS access |
| **Infrastructure subtotal** | **$59–65** | |

**Alternative: Hetzner Cloud CCX33**

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| CCX33 server | $73.99 | 8 dedicated AMD vCPU, 32GB, 240GB SSD |
| Additional volume (200GB) | $9.60 | $0.048/GB/mo |
| Snapshots (50GB) | $0.60 | $0.012/GB/mo |
| **Infrastructure subtotal** | **$84** | |

---

## Model/API Usage Costs

### Usage Assumptions

Based on typical AI coding agent workloads (OpenHands-style):

| Metric | Conservative | Moderate | Heavy |
|--------|-------------|----------|-------|
| Agent sessions/day | 5 | 15 | 30 |
| Avg input tokens/session | 50K | 80K | 120K |
| Avg output tokens/session | 10K | 20K | 40K |
| Monthly input tokens | 7.5M | 36M | 108M |
| Monthly output tokens | 1.5M | 9M | 36M |

### Cost per Model at Moderate Usage (36M input / 9M output per month)

| Model | Input Cost | Output Cost | Monthly Total |
|-------|-----------|-------------|---------------|
| DeepSeek V4-Flash (cache miss) | $5.04 | $2.52 | **$7.56** |
| DeepSeek V4-Flash (50% cache hit) | $2.55 | $2.52 | **$5.07** |
| DeepSeek V4-Pro | $15.66 | $7.83 | **$23.49** |
| Qwen-turbo (DashScope) | $1.80 | $4.50 | **$6.30** |
| Claude Haiku 4.5 | $36.00 | $45.00 | **$81.00** |
| GPT-4.1-mini | $14.40 | $14.40 | **$28.80** |
| Gemini 2.5 Flash | $5.40 | $5.40 | **$10.80** |

### Recommended Monthly API Budget

| Model | Role | Allocation | Est. Cost |
|-------|------|-----------|-----------|
| DeepSeek V4-Flash | Primary (80% of traffic) | 29M in / 7.2M out | $6.05 |
| DeepSeek V4-Pro | Complex tasks (10%) | 3.6M in / 0.9M out | $2.35 |
| Qwen-turbo | Secondary fallback (8%) | 2.9M in / 0.7M out | $0.50 |
| Claude Haiku 4.5 / GPT-4.1-mini | Emergency (2%) | 0.7M in / 0.2M out | $1.70 |
| **API subtotal** | | | **$10.60** |

### Heavy Usage Scenario (108M input / 36M output per month)

| Model | Role | Allocation | Est. Cost |
|-------|------|-----------|-----------|
| DeepSeek V4-Flash | Primary (80%) | 86.4M in / 28.8M out | $20.16 |
| DeepSeek V4-Pro | Complex tasks (10%) | 10.8M in / 3.6M out | $7.83 |
| Qwen-turbo | Secondary (8%) | 8.6M in / 2.9M out | $1.88 |
| Claude Haiku / GPT-4.1-mini | Emergency (2%) | 2.2M in / 0.7M out | $5.70 |
| **API subtotal (heavy)** | | | **$35.57** |

---

## Total Monthly Cost Projections

### Option A: Hetzner Dedicated AX42-U (Recommended)

| Scenario | Infra | API | Total | Under Budget? |
|----------|-------|-----|-------|---------------|
| Conservative | $59 | $5 | **$64** | Yes ($136 buffer) |
| Moderate | $59 | $11 | **$70** | Yes ($130 buffer) |
| Heavy | $59 | $36 | **$95** | Yes ($105 buffer) |
| Extreme (2× heavy) | $59 | $72 | **$131** | Yes ($69 buffer) |

### Option B: Hetzner Cloud CCX33

| Scenario | Infra | API | Total | Under Budget? |
|----------|-------|-----|-------|---------------|
| Conservative | $84 | $5 | **$89** | Yes ($111 buffer) |
| Moderate | $84 | $11 | **$95** | Yes ($105 buffer) |
| Heavy | $84 | $36 | **$120** | Yes ($80 buffer) |

### Option C: OVHcloud Rise-1

| Scenario | Infra | API | Total | Under Budget? |
|----------|-------|-----|-------|---------------|
| Conservative | $70 | $5 | **$75** | Yes ($125 buffer) |
| Moderate | $70 | $11 | **$81** | Yes ($119 buffer) |
| Heavy | $70 | $36 | **$106** | Yes ($94 buffer) |

---

## Break-Even Analysis

At what point does API usage exceed budget?

With AX42-U ($59 infra), you have **$141/month** for API calls.

At DeepSeek V4-Flash rates ($0.14/$0.28 per 1M):
- $141 buys approximately **336M input tokens + 336M output tokens** (mixed)
- That's roughly **1,000+ agent sessions/month** at moderate token usage
- Or **33+ sessions/day** — well beyond typical single-developer needs

**Conclusion:** DeepSeek pricing is so low that API costs are almost negligible relative to infrastructure. Even extreme usage stays well within the $200 budget.

---

## One-Time Costs

| Item | Cost | Notes |
|------|------|-------|
| Hetzner AX42-U setup fee | ~$255 | One-time, non-refundable |
| DeepSeek API initial top-up | $10–50 | Pre-paid balance |
| Domain registration (optional) | $10–15/year | For HTTPS/DNS |
| **One-time total** | **$275–320** | Amortized over first 3 months: +$92–107 |

---

## Cost Optimization Strategies

1. **Maximize cache hits:** DeepSeek V4-Flash cache hit pricing ($0.0028/M) is 50× cheaper than cache miss. Structure prompts to reuse system prompt prefixes.

2. **Use V4-Flash for everything except complex reasoning:** Only escalate to V4-Pro for multi-step debugging or architecture decisions.

3. **Qwen-turbo for simple tasks:** At $0.05/M input, use for linting suggestions, simple completions, documentation generation.

4. **Avoid Claude/OpenAI except emergencies:** 30–100× more expensive than DeepSeek for comparable tasks.

5. **Snapshot before major changes:** On Hetzner dedicated, use Hetzner Storage Box for backups rather than expensive snapshot services.

---

## Comparison to Devin

| | This Setup | Devin (estimated) |
|--|-----------|-------------------|
| Monthly cost | $70–130 | $500+ (seat license) |
| Model flexibility | Full control | Locked to provider |
| Customization | Complete | Limited |
| Multi-session | Git worktrees + tmux | Built-in |
| Persistence | Full | Session-based |
| GPU burst | Add RunPod/Vast.ai | N/A |
