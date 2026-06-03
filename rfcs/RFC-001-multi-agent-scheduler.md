# RFC-001: Multi-Agent Scheduler

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Design a scheduler that orchestrates multiple OpenHands agent sessions on the workstation, managing resource allocation, task queuing, priority, and conflict resolution.

## Motivation

A single agent can only work on one task at a time. With 8 vCPUs and 32GB RAM, the workstation can support 3-4 concurrent agent sessions if properly scheduled. This enables:
- Parallel feature development across branches
- Background tasks (tests, linting) while primary agent works
- CI/CD-like workflows triggered by git events

## Design

### Architecture

```
┌──────────────────┐
│  Scheduler API   │  HTTP :9800
│  (Python/FastAPI) │
└────────┬─────────┘
         │
    ┌────┴────┐
    │  Queue  │  Priority queue (Redis or in-memory)
    └────┬────┘
         │
  ┌──────┼──────┐
  ▼      ▼      ▼
┌────┐ ┌────┐ ┌────┐
│ W1 │ │ W2 │ │ W3 │   Workers (worktree + tmux + agent)
└────┘ └────┘ └────┘
```

### Resource Limits

| Resource | Per Worker | Maximum Workers |
|----------|-----------|-----------------|
| vCPUs | 2 | 4 |
| RAM | 6 GB | 4 (with 8GB system reserve) |
| Ports | 10 (range) | 10 |
| Storage | Shared | — |

### Task Schema

```yaml
task:
  id: uuid
  repo: github.com/user/project
  branch: feature/new-api
  prompt: "Implement the /users endpoint"
  priority: 1-10
  resources:
    cpu_limit: 2
    memory_limit: 6g
  constraints:
    max_duration: 30m
    model: deepseek-v4-flash
    budget: $0.50
```

### Scheduling Algorithm

1. FIFO within priority bands
2. Resource-fit check before dispatch
3. Preemption for priority >= 9
4. Automatic cleanup after task completion/timeout

## API Endpoints

- `POST /tasks` — Submit new task
- `GET /tasks` — List queued/active tasks
- `DELETE /tasks/:id` — Cancel task
- `GET /workers` — Worker status
- `GET /metrics` — Scheduler metrics

## Dependencies

- Worktree scripts (implemented)
- LiteLLM budget limits
- OpenHands API (for programmatic agent launch)

## Open Questions

1. Should workers share a single OpenHands instance or each run their own?
2. How to handle agent-to-agent communication (e.g., one agent's output feeds another)?
3. Integration with git hooks for automatic task triggering?
