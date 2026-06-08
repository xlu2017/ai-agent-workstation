# Runtime Adapters and Execution Architecture

## Overview

jubilant-goggles implements a layered execution architecture that connects advisory plans from agent-core to actual code execution through durable workflows, composite action subflows, and execution backends.

```
LLM proposes.
agent-core validates action contracts.
jubilant-goggles authorizes and executes.
```

## System Boundary

```
agent-core owns:
  - Memory and repo context
  - Action catalog and schema validation
  - LLM-first action planning
  - Plan validation
  - Trace/outcome storage

jubilant-goggles owns:
  - Live feed and prompt routing
  - Sessions and worktrees
  - Durable workflow execution (Hatchet)
  - Runtime validation (permissions, paths, sessions)
  - Composite action subflows (LangGraph)
  - Execution backends (OpenHands, fallback)
  - Commits and PRs

Repo context adapters must NOT be added to jubilant-goggles.
jubilant-goggles consumes agent-core context APIs only.
```

## Execution Flow

```
User prompt
  → jubilant-goggles session route
  → prompt router (6 routing decisions)
  → agent-core POST /actions/plan
  → agent-core POST /actions/validate-plan
  → WorkflowAdapter.start_plan()
  → Hatchet execute_agent_plan workflow
  → per-step runtime validation
  → if atomic action:
       ExecutionRouter → OpenHands or Fallback
  → if composite action:
       CompositeActionRouter → LangGraph → ExecutionRouter → OpenHands/Fallback
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

| Adapter | Backend | Actions |
|---------|---------|---------|
| `OpenHandsExecutorAdapter` | OpenHands | All coding actions (primary) |
| `FallbackExecutorAdapter` | Local subprocess | grep, read_file, run_tests, summarize_diff, commit, apply_patch |

OpenHands is the primary coding execution backend. The fallback executor is for dev/test only.

Configuration:
```
EXECUTOR_BACKEND=openhands | fallback
OPENHANDS_ENABLED=true
OPENHANDS_BASE_URL=http://localhost:...
OPENHANDS_WORKSPACE_BASE=/opt/workstation/repos
ALLOW_FALLBACK_EXECUTOR=false
```

ExecutionRouter rules:
1. `EXECUTOR_BACKEND=openhands` → OpenHands
2. `EXECUTOR_BACKEND=fallback` → Fallback
3. Default: OpenHands if `OPENHANDS_ENABLED=true`, else fallback if `ALLOW_FALLBACK_EXECUTOR=true`, else fail

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

### 5. execute_agent_plan Workflow

The core workflow that runs an advisory plan step-by-step:

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
  9. Emit ACTION_COMPLETED or ACTION_FAILED
  10. Record outcome to agent-core
  11. If commit succeeded → COMMIT_CREATED
```

Plan modes:
- **finite**: Run steps once
- **loop**: Run once, emit PLAN_COMPLETED with `needs_refresh=true`
- **open_ended**: Run once, emit PLAN_COMPLETED with `needs_refresh=true`

No uncontrolled infinite loops.

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
EXECUTOR_BACKEND=openhands
LANGGRAPH_ENABLED=false
ALLOW_FALLBACK_EXECUTOR=false
ALLOW_FALLBACK_COMPOSITE_ACTIONS=false
```

Test:
```
WORKFLOW_BACKEND=inprocess
EXECUTOR_BACKEND=fallback
ALLOW_FALLBACK_EXECUTOR=true
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
│   │   ├── openhands_adapter.py  — OpenHands backend
│   │   ├── fallback_adapter.py   — Local fallback executor
│   │   └── router.py             — ExecutionRouter
│   └── composite_action/
│       ├── base.py               — CompositeActionAdapter ABC
│       ├── langgraph_adapter.py  — LangGraph composite subflows
│       └── router.py             — CompositeActionRouter
├── execution/
│   └── runtime_validator.py      — Pre-execution platform validation
├── workflows/
│   └── execute_agent_plan.py     — Plan executor (Hatchet workflow logic)
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
