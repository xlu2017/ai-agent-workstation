# Provider Comparison

## Infrastructure Providers

| Provider | Plan | vCPUs | RAM | Storage | Traffic | Monthly | Hourly | Stop Billing |
|----------|------|-------|-----|---------|---------|---------|--------|--------------|
| **Hetzner Cloud** | CCX33 (dedicated) | 8 | 32 GB | 240 GB | 30 TB | $73.99 | $0.119 | Delete + snapshot |
| Hetzner Cloud | CPX51 (shared) | 16 | 32 GB | 360 GB | 30 TB | ~$65* | ~$0.10 | Delete + snapshot |
| Hetzner Cloud | CCX43 (dedicated) | 16 | 64 GB | 360 GB | 40 TB | $147.49 | $0.236 | Delete + snapshot |
| OVHcloud | B2-30 | 8 | 30 GB | 200 GB | unlimited | ~$55 | — | Monthly only |
| DigitalOcean | Premium 32GB | 8 | 32 GB | 400 GB | 7 TB | $126 | $0.188 | Delete + snapshot |
| AWS EC2 | m6a.2xlarge | 8 | 32 GB | EBS | pay/GB | ~$140 | $0.192 | Stop (EBS only) |

*CPX51 pricing post April 2026 adjustment — Hetzner page no longer shows exact USD figures inline.

## Selection: Hetzner Cloud CCX33

**Justification:**
1. **Best price/performance** for dedicated CPU at $74/mo
2. **Hourly billing** with monthly cap — only pay for what you use
3. **Pause/resume** via snapshot ($0.36/mo while paused) — no setup fees
4. **Excellent Docker support** — official Ubuntu images with Docker pre-installable
5. **European data centers** — low latency to API providers, GDPR compliant
6. **240 GB SSD** sufficient for development (expandable with volumes at $0.052/GB/mo)

**Why not others:**
- **CPX51**: More vCPUs but shared — noisy neighbor risk during Docker builds
- **CCX43**: Over budget at $147/mo, unnecessary 64GB RAM
- **OVHcloud**: Monthly-only billing, no hourly option, weaker API
- **DigitalOcean**: 70% more expensive for same specs
- **AWS EC2**: Complex pricing, egress charges, 90% more expensive

## Model API Providers

| Provider | Model | Input ($/1M) | Output ($/1M) | Cache Hit | Context | Latency |
|----------|-------|--------------|---------------|-----------|---------|---------|
| **DeepSeek** | V4-Flash | $0.14 | $0.28 | $0.014 | 64K | ~1.5s |
| DeepSeek | V3 | $0.27 | $1.10 | $0.07 | 64K | ~2s |
| DashScope | Qwen-turbo | $0.05 | $0.50 | — | 128K | ~1s |
| DashScope | Qwen-plus | $0.40 | $1.20 | — | 128K | ~2s |
| Anthropic | Claude Haiku 3.5 | $0.80 | $4.00 | — | 200K | ~1.5s |
| OpenAI | GPT-4.1-mini | $0.40 | $1.60 | — | 128K | ~1s |
| Google | Gemini 2.5 Flash | $0.15 | $0.60 | — | 1M | ~1.5s |

## Model Selection Strategy

**Primary: DeepSeek V4-Flash** ($0.14/$0.28 per 1M tokens)
- Best cost/quality ratio for code generation
- 10x cheaper than Claude Haiku
- Excellent at code completion, refactoring, debugging

**Secondary: DashScope Qwen-turbo** ($0.05/$0.50 per 1M tokens)
- Cheapest option for simple tasks
- Good for code review, documentation, translations
- 128K context for large file analysis

**Fallback: Anthropic Claude / OpenAI GPT-4.1-mini**
- Only for tasks where DeepSeek/Qwen fail
- Budget-capped to prevent cost overruns

Sources:
- https://api-docs.deepseek.com/quick_start/pricing
- https://help.aliyun.com/zh/model-studio/getting-started/models
- https://www.anthropic.com/pricing
- https://openai.com/api/pricing
- https://ai.google.dev/pricing
