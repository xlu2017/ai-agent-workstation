# RFC-006: Burst GPU Workers via RunPod

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Use RunPod serverless or on-demand GPU instances for tasks requiring GPU acceleration: local model inference, image generation, large context processing, and Android emulator rendering.

## Motivation

The Hetzner workstation has no GPU. Some tasks benefit from GPU:
- **Local LLM inference** — Run DeepSeek-V3 (or smaller models) locally for privacy/speed
- **Code embeddings** — Generate embeddings for codebase search
- **Image generation** — UI mockups, icons, diagrams
- **Android emulator** — Hardware-accelerated rendering (see RFC-005)

## Architecture

```
┌─────────────────────┐        ┌─────────────────────────┐
│  Hetzner Workstation│        │  RunPod GPU Worker      │
│  (always-on)        │        │  (on-demand)            │
│                     │  API   │                         │
│  LiteLLM ──────────┼────────┼──→ vLLM / Ollama       │
│                     │        │     (DeepSeek-V3)       │
│  Agent ─────────────┼────────┼──→ Embedding service    │
│                     │        │                         │
└─────────────────────┘        └─────────────────────────┘
                                   Billed per second
```

## RunPod Options

### Serverless (recommended for burst)
- Pay per second of compute
- Auto-scales to zero
- Cold start: 5-30 seconds
- GPUs: A100, H100, A6000

### On-Demand (for sustained workloads)
- Reserve specific GPU
- No cold start
- Minimum billing: 1 minute
- Better for multi-hour inference sessions

## Cost Estimates

| GPU | $/hr | Use Case | Monthly (10 hrs) |
|-----|------|----------|-----------------|
| RTX 4090 | $0.44 | Light inference | $4.40 |
| A100 80GB | $1.64 | Large models | $16.40 |
| H100 | $3.89 | Maximum speed | $38.90 |

## LiteLLM Integration

```yaml
# In litellm_config.yaml
model_list:
  - model_name: deepseek-local
    litellm_params:
      model: openai/deepseek-v3
      api_base: http://runpod-worker:8000/v1
      api_key: os.environ/RUNPOD_API_KEY
    model_info:
      description: "Self-hosted DeepSeek on RunPod GPU (on-demand)"
```

## Workflow

1. User/agent requests model that requires GPU
2. LiteLLM routes to RunPod endpoint
3. RunPod cold-starts worker (if serverless)
4. Inference runs on GPU
5. Worker auto-stops after idle timeout

## Security

- RunPod workers in isolated containers
- API key authentication
- No persistent storage (stateless)
- Code never leaves Hetzner unless explicitly sent

## Open Questions

1. Cold start latency acceptable for interactive use?
2. Should we pre-warm workers during business hours?
3. Cost monitoring and automatic shutdown thresholds?
4. Which models to self-host vs use APIs?
