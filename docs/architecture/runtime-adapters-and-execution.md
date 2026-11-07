# Runtime Adapters and Execution Architecture

## Overview

ai-agent-workstation implements a layered execution architecture that connects advisory plans from agent-core to actual code execution through durable workflows, composite action subflows, and execution backends.

```
LLM proposes.
agent-core validates action contracts.
ai-agent-workstation authorizes and executes.
```

## System Boundary

```
agent-core owns:
  - Memory and repo context
  - Action catalog and schema validation
  - LLM-first action planning
  - Plan validation
  - Trace/outcome storage

ai-agent-workstation owns:
  - Live feed and prompt routing
  - Sessions and worktrees
  - Durable workflow execution (Hatchet)
  - Runtime validation (permissions, paths, sessions)
  - Composite action subflows (LangGraph)
  - Execution backends (AgenticExecutor, DeterministicExecutor)
  - Commits and PRs

Repo context adapters must NOT be added to ai-agent-workstation.
ai-agent-workstation consumes agent-core context APIs only.
```

## Execution Flow

```
User prompt
  → ai-agent-workstation session route
  → prompt router (6 routing decisions)
  → agent-core POST /actions/plan
  → agent-core POST /actions/validate-plan
  → WorkflowAdapter.start_plan()
  → Hatchet execute_agent_plan workflow
  → per-step runtime validation
  → if atomic action:
       ExecutionRouter → AgenticExecutor or DeterministicExecutor
  → if composite action:
       CompositeActionRouter → LangGraph → ExecutionRouter → AgenticExecutor/DeterministicExecutor
  → live feed events (ACTION_STARTED, ACTION_COMPLETED, etc.)
  → agent-core POST /actions/outcome
```

## Architecture Layers

### 1. WorkflowAdapter (Durable Execution)

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `HatchetWorkflowAdapter` | Hatchet SDK | Production durable workflows |
| `InProcessWorkflowAdapter` | asyncio.create_task | Dev/test only, not durable |

Hatchet is the durable workflow runner. It ensures plans survive process restarts and provides reliable step-by-step execution.

InProcess adapter runs the workflow coroutine directly — for testing only.

Configuration:
```
WORKFLOW_BACKEND=hatchet | inprocess
HATCHET_ENABLED=true
HATCHET_SERVER_URL=...
HATCHET_CLIENT_TOKEN=...
```

### 2. ExecutionAdapter (Action Backends)

| Executor | Backend Name | Actions |
|----------|-------------|---------|
| `AgenticExecutor` | `agentic` | Primary local agentic coding executor — LLM tool-calling loop for bounded actions (autonomous_code_edit, investigate_and_patch, repair_test_failure, apply_patch with intent) |
| `DeterministicExecutor` | `deterministic` | Fast deterministic executor for simple local operations (grep, read_file, list_files, apply_patch with exact content, run_tests with explicit command, commit) |

**AgenticExecutor** is the primary coding execution backend. It uses a local LLM tool-calling loop to inspect files, edit files, run commands, and emit granular events. It executes one bounded assigned action and does not decide the next platform step after its assigned action completes.

**DeterministicExecutor** is the fast simple/fallback executor for cheap, direct actions. No LLM loop, no autonomous decisions.

Configuration:
```
EXECUTOR_BACKEND=agentic | deterministic
AGENTIC_EXECUTOR_ENABLED=true
AGENTIC_EXECUTOR_MAX_ITERATIONS=50
AGENTIC_EXECUTOR_COMMAND_TIMEOUT=60
ALLOW_DETERMINISTIC_EXECUTOR=true
```

ExecutionRouter rules:
1. `EXECUTOR_BACKEND=agentic` → AgenticExecutor
2. `EXECUTOR_BACKEND=deterministic` → DeterministicExecutor
3. Default: AgenticExecutor if `AGENTIC_EXECUTOR_ENABLED=true`, else DeterministicExecutor if `ALLOW_DETERMINISTIC_EXECUTOR=true`, else fail
4. Context-aware routing: `apply_patch` with `intent` → agentic; `apply_patch` with `patch`/`content` → deterministic; `run_tests` with repair → agentic; `run_tests` with explicit command → deterministic

### 3. CompositeActionAdapter (Multi-Step Subflows)

LangGraph is **not** the durable workflow runner. It is used inside selected Hatchet steps for composite/agentic actions that require internal loops.

Composite actions:
- `autonomous_code_edit`
- `repair_test_failure`
- `browser_debug_loop`
- `multi_file_refactor_loop`
- `investigate_and_patch`

Atomic actions go directly to ExecutionRouter:
- `grep`, `read_file`, `apply_patch`, `run_tests`, `summarize_diff`, `commit`

Configuration:
```
LANGGRAPH_ENABLED=true
ALLOW_FALLBACK_COMPOSITE_ACTIONS=false
```

### 4. RuntimeValidator

Validates before execution (separate from agent-core schema validation):
- Session exists
- Worktree exists
- Action in session.allowed_actions
- Path params don't escape worktree
- Commit requires allowed_actions + non-empty message
- Composite actions require LangGraph enabled or fallback mode

### 5. execute_agent_plan Workflow (PlanExecutor)

The core workflow that runs an advisory plan step-by-step.

**PlanExecutor is the action sequence runner, not the planner.** agent-core is the planner and validator, not the executor.

Core invariant:
- Executor decides **how** to complete the current assigned action.
- Planner decides **what** action should happen next.
- Workflow decides **when** to ask for another plan.
- Platform decides **whether** an action is allowed.

```
for each step:
  1. Reload session state
  2. Check cancelled → stop
  3. Check paused → return
  4. Emit ACTION_STARTED
  5. Runtime validate
  6. If blocked → ACTION_BLOCKED, record outcome
  7. Route: atomic → ExecutionRouter, composite → CompositeActionRouter
  8. Execute
  9. Append executor events to EventStore (redacted, filtered)
  10. Emit ACTION_COMPLETED or ACTION_FAILED
  11. Record outcome to agent-core (redacted output/error)
  12. If commit succeeded → COMMIT_CREATED
```

Plan modes:
- **finite**: Run steps once
- **loop**: Run once, emit PLAN_COMPLETED with `needs_refresh=true`
- **open_ended**: Run once, emit PLAN_COMPLETED with `needs_refresh=true`

No uncontrolled infinite loops.

### 6. Redaction

Central redaction helper (`execution/redaction.py`) strips secrets from all outputs before they reach events, API responses, or agent-core outcome records.

Redacted patterns:
- `ghp_*`, `github_pat_*`, `sk-*`, `tskey-*`, Bearer tokens, Authorization headers
- `password=`, `RDP_PASSWORD`, `TAILSCALE_AUTH_KEY`, `PAT` values, SSH private keys

Allowed through:
- `secret_name`, `secret_ref`, `$PAT` as a label

## Execution Result Contract

All executors return a normalized `ExecutionResult`:

```python
{
    "status": "succeeded | failed | blocked | skipped | cancelled | needs_review",
    "backend": "agentic | deterministic",
    "summary": "string",
    "output": {},
    "error": "",
    "files_touched": [],
    "events": [],
    "duration_ms": 0,
    "redacted": true
}
```

Executor events use normalized `ExecutionEvent`:

```python
{
    "event_type": "action_progress | command_executed | file_read | file_edited | file_created | test_completed | agent_error",
    "title": "short title",
    "summary": "short user-visible summary",
    "status": "running | completed | failed | blocked | skipped",
    "metadata": {},
    "redacted": true,
    "source": "agentic | deterministic"
}
```

## Event Types

```
PLAN_REQUESTED      — plan generation requested
PLAN_GENERATED      — plan received from agent-core
PLAN_VALIDATION_FAILED — plan failed schema/sequence validation
PLAN_STARTED        — workflow started executing plan
ACTION_STARTED      — individual action execution began
ACTION_PROGRESS     — composite action substep progress
ACTION_BLOCKED      — action blocked by runtime validator
ACTION_COMPLETED    — action succeeded
ACTION_FAILED       — action failed
PLAN_PAUSED         — workflow paused
PLAN_RESUMED        — workflow resumed
PLAN_CANCELLED      — workflow cancelled
PLAN_COMPLETED      — all steps finished
COMMIT_CREATED      — real commit succeeded (never faked)
```

## Default Configuration

Production:
```
WORKFLOW_BACKEND=hatchet
EXECUTOR_BACKEND=agentic
AGENTIC_EXECUTOR_ENABLED=true
LANGGRAPH_ENABLED=false
ALLOW_DETERMINISTIC_EXECUTOR=false
ALLOW_FALLBACK_COMPOSITE_ACTIONS=false
```

Test:
```
WORKFLOW_BACKEND=inprocess
EXECUTOR_BACKEND=deterministic
ALLOW_DETERMINISTIC_EXECUTOR=true
```

## File Layout

```
control-plane/
├── adapters/
│   ├── workflow/
│   │   ├── base.py               — WorkflowAdapter ABC
│   │   ├── hatchet_adapter.py    — Hatchet SDK integration
│   │   └── inprocess_adapter.py  — Dev/test asyncio adapter
│   ├── execution/
│   │   ├── base.py               — ExecutionAdapter ABC
│   │   ├── openhands_adapter.py  — Compatibility shim → AgenticExecutor
│   │   ├── fallback_adapter.py   — Compatibility shim → DeterministicExecutor
│   │   └── router.py             — ExecutionRouter (capability-aware)
│   └── composite_action/
│       ├── base.py               — CompositeActionAdapter ABC
│       ├── langgraph_adapter.py  — LangGraph composite subflows
│       └── router.py             — CompositeActionRouter
├── execution/
│   ├── __init__.py               — Package init
│   ├── agentic_executor.py       — AgenticExecutor (LLM tool-calling loop)
│   ├── deterministic_executor.py — DeterministicExecutor (fast direct actions)
│   ├── results.py                — ExecutionResult / ExecutionEvent contracts
│   ├── redaction.py              — Central secret redaction
│   ├── router.py                 — Canonical ExecutionRouter
│   ├── prompt_handler.py         — End-to-end prompt orchestration
│   └── runtime_validator.py      — Pre-execution platform validation
├── executors/
│   ├── base.py                   — TaskPacket / ExecutorResult
│   ├── openhands_adapter.py      — Compatibility shim → AgenticExecutor
│   ├── openhands_executor.py     — Compatibility shim → AgenticExecutor
│   └── direct_executor.py        — Compatibility shim → AgenticExecutor
├── workflows/
│   └── execute_agent_plan.py     — PlanExecutor (Hatchet workflow logic)
├── sessions/
│   ├── controller.py             — Wired to agent-core + WorkflowAdapter
│   ├── routes.py                 — Async FastAPI endpoints
│   └── models.py                 — Session/SessionStore
└── tests/
    ├── test_workflow_adapters.py
    ├── test_execution_adapters.py
    ├── test_langgraph_composite_adapter.py
    └── test_end_to_end_execution.py
```
