# Live Feed and Concurrent Prompt Routing

## Overview

jubilant-goggles implements a live event stream and concurrent prompt routing system that enables users to submit prompts at any time during plan execution. The platform decides how to handle each new prompt — whether to append it, modify the current plan, interrupt, spawn a child session, start a new session, or queue it.

This is the execution and orchestration counterpart to agent-core's advisory planning. The boundary is:

```
agent-core validates action contracts.
jubilant-goggles validates runtime permissions and executes.
agent-core may return loop/open-ended/commit-capable plans.
jubilant-goggles decides whether commits actually happen.
Users may submit prompts at any time during execution.
```

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  User / UI                                           │
│  ├─ POST /api/v2/sessions/:id/prompts  (new prompt)  │
│  ├─ POST /api/v2/sessions/:id/control  (pause/stop)  │
│  └─ GET  /api/v2/sessions/:id/events/stream  (SSE)   │
└──────────┬───────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│  Prompt Router                                       │
│  ├─ detect_control_command()                         │
│  ├─ route_prompt() → RoutingDecision                 │
│  └─ Decisions: append | modify | interrupt |         │
│     spawn_child | spawn_new | queue                  │
└──────────┬───────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│  Session Controller                                  │
│  ├─ create_session()                                 │
│  ├─ handle_prompt()  → route → execute decision      │
│  ├─ handle_control() → pause/resume/cancel           │
│  └─ Records all events to EventStore                 │
└──────────┬───────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│  agent-core (HTTP)                                   │
│  ├─ POST /actions/plan       (plan generation)       │
│  ├─ POST /actions/validate   (deterministic check)   │
│  ├─ POST /actions/outcome    (record what happened)  │
│  └─ POST /memory/search      (memory retrieval)      │
└──────────────────────────────────────────────────────┘
```

## Endpoints

### Session Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v2/sessions` | Create a session (root, child, parallel, queued) |
| `GET` | `/api/v2/sessions` | List sessions with optional filters |
| `GET` | `/api/v2/sessions/:id` | Get session details |

### Prompt Intake

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v2/sessions/:id/prompts` | Submit a prompt during execution |

The platform:
1. Records a `user_prompt_received` event
2. Loads current session state
3. Routes the prompt deterministically
4. Records a `routing_decision_made` event
5. Executes the routing decision

### Control Commands

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v2/sessions/:id/control` | Send control command |

Supported commands: `pause`, `resume`, `cancel`, `commit_checkpoint`

### Live Event Stream

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v2/sessions/:id/events/stream` | SSE live feed |
| `GET` | `/api/v2/sessions/:id/events` | Paginated event history |

### Concurrency

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v2/sessions/:id/concurrency` | Worktree claim info |
| `POST` | `/api/v2/sessions/:id/concurrency/claim` | Claim a worktree |
| `POST` | `/api/v2/sessions/:id/concurrency/release` | Release a worktree claim |

## Event Types

All events are append-only and stored as JSONL:

```
user_prompt_received     — user submitted a prompt
routing_decision_made    — platform decided how to handle the prompt
plan_requested           — plan generation requested from agent-core
plan_generated           — plan received from agent-core
plan_validation_failed   — deterministic validation failed
plan_started             — plan execution began
action_started           — individual action started
action_progress          — action progress update
action_blocked           — action blocked (needs approval, etc.)
action_completed         — action finished successfully
action_failed            — action failed
plan_paused              — plan paused by user or platform
plan_resumed             — plan resumed
plan_cancelled           — plan cancelled
plan_completed           — plan finished
child_session_started    — child session spawned
memory_extracted         — lesson/memory extracted from execution
commit_created           — git commit created
pr_created               — pull request created
```

## Session Types

| Type | Description |
|------|-------------|
| `root_session` | Initial user task |
| `child_session` | Related task sharing repo/worktree/context lineage |
| `parallel_session` | Independent task, usually separate worktree |
| `queued_session` | Task waiting for resources or user approval |

Each session persists: `parent_session_id`, `root_session_id`, `repo_id`, `worktree_id`, `executor_id`, `status`, `active_plan_id`, `created_from_prompt_id`.

## Prompt Routing

The router uses deterministic heuristics to classify incoming prompts:

| Pattern | Decision |
|---------|----------|
| "stop" / "cancel" / "abort" | `interrupt_current` |
| "pause" | `interrupt_current` |
| "resume" / "continue" | `append_to_current` |
| "commit what is done" | `append_to_current` (with commit_checkpoint) |
| "also..." / "check..." / "fix..." | `modify_current_plan` |
| "new task..." / "different task..." | `spawn_child_session` (same repo) |
| "work on another repo" | `spawn_new_session` |
| Short prompt, plan running | `append_to_current` (clarification) |
| Long prompt, plan running | `modify_current_plan` |
| No plan running | `append_to_current` |

## Concurrency Rules

1. **One mutating executor per worktree.** Two sessions cannot both write to the same worktree.
2. **Parallel read-only sessions may share a repo checkout.**
3. **Parallel mutating sessions require separate worktrees.**
4. **Commits require platform validation.** agent-core may propose commits; jubilant-goggles decides.
5. **PRs require platform validation.**
6. **File conflict detection.** If two sessions touch overlapping files, a conflict event is surfaced.

## agent-core Integration

jubilant-goggles calls agent-core for:

| Endpoint | Purpose |
|----------|---------|
| `POST /actions/plan` | Generate an advisory plan |
| `POST /actions/validate-plan` | Deterministic plan validation |
| `POST /actions/outcome` | Record what was actually executed |
| `POST /actions/recommend-next` | Stepwise next-action recommendation |
| `GET /actions` | Fetch the action catalog |
| `POST /memory/search` | Search memories |

jubilant-goggles does NOT ask agent-core to: execute, schedule, pause, cancel, commit, create worktrees, create branches, or create PRs.

## Truthful Status

Sessions maintain truthful state — not just "created" / "working" / "done":

```
created → claimed → planning → editing → validating → committed → completed
                                      → failed
                                      → blocked
                  → paused → (resumed)
                  → cancelled
                  → answered
```
