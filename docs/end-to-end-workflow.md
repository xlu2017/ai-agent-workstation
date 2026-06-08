# End-to-End Workflow

## Architecture Principle

```
Memory proposes.
Retrieval supplies context.
Action knowledge recommends.
Tool rules constrain.
Policy authorizes.
Executors execute.
Control plane records everything.
```

## System Boundary

```
agent-core (advisory only):
  memory / retrieval / context
  action catalog + schema validation
  advisory planning (LLM-first)
  rule solving + recommendations
  trace storage

jubilant-goggles (authoritative execution):
  sessions / worktrees
  runtime adapters (OpenHands)
  Hatchet queue integration
  LangGraph single-action workflows
  runtime policy + approvals
  path/command guards
  live feed + status feed
  commits + PRs (approval-gated)
```

## Prompt Flow

```
User prompt
  → POST /api/sessions/:id/chat
  → prompt_router classifies: ask / do / explore / fix / fork-and-prove / full-autonomy
  → runtime policy checks (session, paths, commands, approvals)
  → agent-core POST /actions/plan (advisory only)
  → agent-core POST /actions/validate-plan (advisory only)
  → OpenHands executor adapter runs the task
  → live feed emits truthful events
  → status feed narrates for user
  → GET /api/sessions/:id/state returns truthful state
  → commit/PR remains approval-gated
```

## Truthful State Machine

Sessions report truthful state, never guessing:

| State | Meaning |
|-------|---------|
| `received` | Prompt acknowledged |
| `routing` | Classifying intent |
| `planning` | Requesting advisory plan from agent-core |
| `queued` | Waiting for available slot |
| `executor_starting` | OpenHands conversation starting |
| `executor_running` | OpenHands actively executing |
| `editing` | Files being modified |
| `validating` | Tests/lint/build running |
| `blocked` | Cannot proceed (policy, approval, or unavailability) |
| `failed` | Execution error |
| `completed` | Finished successfully |
| `needs_review` | Human review required |
| `committed` | Changes committed to branch |

## Key Endpoints

### Control Plane (jubilant-goggles)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | System health check |
| `POST /api/sessions` | Create session |
| `GET /api/sessions` | List sessions |
| `GET /api/sessions/:id` | Inspect session |
| `DELETE /api/sessions/:id` | Destroy session |
| `POST /api/sessions/:id/chat` | Submit prompt for execution |
| `GET /api/sessions/:id/state` | Truthful execution state |
| `GET /api/sessions/:id/events` | Raw event log |
| `GET /api/sessions/:id/timeline` | Timeline with summaries |

### agent-core (advisory)

| Endpoint | Purpose |
|----------|---------|
| `GET /actions` | Action catalog |
| `GET /actions/:name` | Action details |
| `POST /actions/plan` | Advisory plan generation |
| `POST /actions/validate-plan` | Plan shape validation |
| `POST /actions/validate` | Action contract validation |
| `POST /actions/recommend-next` | Next-action recommendation |
| `POST /actions/mock-execute` | Simulation only (not live) |
| `POST /actions/simulate-pipeline` | Pipeline simulation (not live) |

## OpenHands as Canonical Executor

OpenHands is the only production execution backend. The `OpenHandsExecutorAdapter`:

1. Creates a conversation via POST /conversations
2. Sends the instruction via POST /conversations/:id/run
3. Polls for completion via GET /conversations/:id
4. Collects events, diffs, and results
5. Returns structured TaskResult to the control plane

If OpenHands is unavailable, the system reports `blocked` state — it never silently succeeds.

## Hatchet Queue (if active)

Hatchet provides durable workflow scheduling. When present:
- Sessions are submitted as Hatchet workflows
- Steps execute via OpenHands adapter
- Pause/resume/cancel use Hatchet control mechanisms
- Task durability survives process restarts

## LangGraph (if active)

LangGraph is used only for single composite-action substep workflows (e.g., `autonomous_code_edit`, `repair_test_failure`). It is **not** the global session planner.

## Runtime Policy

Before any execution, the control plane checks:
- Session exists and is runnable
- Action is in allowed set
- Paths stay inside worktree
- Commands are not blocked
- Mutations require approval if configured
- Commit/push/deploy are gated

## Running the Smoke Test

```bash
bash scripts/smoke_end_to_end.sh
```

Or pytest-based:
```bash
pytest control-plane/tests/test_end_to_end_smoke.py -q
```

## CLI

```bash
python control-plane/cli/platformctl.py session list
python control-plane/cli/platformctl.py session create --name my-session --task "fix bug"
python control-plane/cli/platformctl.py session inspect my-session
python control-plane/cli/platformctl.py health
python control-plane/cli/platformctl.py models list
python control-plane/cli/platformctl.py knowledge list
```
