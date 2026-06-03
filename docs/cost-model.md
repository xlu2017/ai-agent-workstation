# Cost Model

## Monthly Budget: $200/month target

## Fixed Costs

| Item | Monthly | Notes |
|------|---------|-------|
| Hetzner Cloud CCX33 | $73.99 | 8 dedicated vCPU, 32GB RAM, 240GB SSD |
| IPv4 address | $0.60 | Required for SSH/RDP access |
| Extra volume (260GB) | $13.52 | To reach 500GB total ($0.052/GB/mo) |
| **Subtotal** | **$88.11** | |

## Variable Costs (API Usage)

### Conservative (light usage: ~5 agent sessions/day)

| Provider | Tokens/day | Monthly Cost |
|----------|-----------|-------------|
| DeepSeek V4-Flash | ~500K in + 200K out | $3.50 |
| DashScope Qwen | ~100K in + 50K out | $0.20 |
| **Subtotal** | | **$3.70** |

### Moderate (active development: ~20 sessions/day)

| Provider | Tokens/day | Monthly Cost |
|----------|-----------|-------------|
| DeepSeek V4-Flash | ~2M in + 800K out | $14.00 |
| DashScope Qwen | ~500K in + 200K out | $1.50 |
| Claude/GPT fallback | ~100K in + 50K out | $3.00 |
| **Subtotal** | | **$18.50** |

### Heavy (production: ~50 sessions/day)

| Provider | Tokens/day | Monthly Cost |
|----------|-----------|-------------|
| DeepSeek V4-Flash | ~5M in + 2M out | $35.00 |
| DashScope Qwen | ~1M in + 500K out | $5.00 |
| Claude/GPT fallback | ~500K in + 200K out | $15.00 |
| **Subtotal** | | **$55.00** |

## Total Monthly Projections

| Scenario | Infrastructure | APIs | Total | % of Budget |
|----------|---------------|------|-------|-------------|
| Paused | $0.36 (snapshot) | $0 | **$0.36** | 0.2% |
| Light | $88.11 | $3.70 | **$91.81** | 46% |
| Moderate | $88.11 | $18.50 | **$106.61** | 53% |
| Heavy | $88.11 | $55.00 | **$143.11** | 72% |
| Extreme | $88.11 | $100.00 | **$188.11** | 94% |

All scenarios remain under $200/month budget.

## Cost Optimization Strategies

1. **DeepSeek cache hits**: Repeated prompts get 90% discount ($0.014/1M)
2. **Pause when idle**: Delete server + keep snapshot = $0.36/mo
3. **Qwen for simple tasks**: Route documentation/formatting to cheapest model
4. **Budget limits in LiteLLM**: Hard cap per model per day
5. **Volume only when needed**: Detach volume when server is paused ($13.52/mo saved)

## Future: Dedicated Hardware Migration

After 6+ months of continuous use:

| Item | One-time | Monthly | Payback |
|------|----------|---------|---------|
| Hetzner AX42-U setup | $255 | — | — |
| AX42-U monthly | — | $59 | 3 months vs CCX33 |
| **Net savings** | | **$29/mo** after payback | |

Break-even: 9 months (setup fee / monthly savings).
