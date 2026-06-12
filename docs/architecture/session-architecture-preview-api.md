# Session Architecture Preview API

## Intent

`control-plane/api/session_architecture.py` provides a preview-only router for session architecture changes. It exposes deterministic planning endpoints that return a `SessionArchitecturePlan` without mutating the session graph.

The router is intentionally separate from the existing `/api/session-graph` execution routes. Preview and apply remain two steps:

```text
preview session architecture proposal
→ inspect returned SessionUpdateProposal or MountSessionRequest
→ call /api/session-graph/session-update/apply to persist
```

This keeps the planner from becoming an execution or authorization layer.

## Router

```text
prefix: /api/session-architecture
tag: session-architecture
```

The router is scaffolded but should be explicitly mounted in `control-plane/api/server.py` before it is available from the running FastAPI app.

Expected server wiring:

```python
from api.session_architecture import router as session_architecture_router

app.include_router(session_architecture_router)
```

## Endpoints

### `POST /api/session-architecture/preview/create-root`

Create a root session proposal from a seed.

Use for newly connected repo, app, container, memory, or goal roots.

### `POST /api/session-architecture/preview/create-child`

Create a child session under an existing parent.

Use for goal under app, work under goal, validation under work, or artifact under work.

### `POST /api/session-architecture/preview/create-sibling`

Create a sibling session in the same root context.

Use when the user starts a related but separate task while the current session continues.

### `POST /api/session-architecture/preview/move-under`

Propose moving any session under any other session through the non-destructive mount/adapt contract.

Examples:

```text
repo → goal
repo → app
work → app
question → work
runtime → repo
memory → goal
```

If the source and target kinds differ, the source is broad and the target is focused, or the user intent is long/ambiguous, the planner sets `create_adaptation_session=true`.

### `POST /api/session-architecture/preview/question-only`

Return a no-graph-change proposal for answer-only prompts.

### `POST /api/session-architecture/preview/context-sources`

Return deterministic candidate source session IDs for future context projection.

This is placeholder ranking logic. A retrieval-backed context router can replace the scoring later without changing the response contract.

## Contract

The preview API returns:

```json
{
  "plan": {
    "intent": "move_under",
    "proposal": {
      "classification": "adapt_session",
      "active_session_id": "goal",
      "mount_request": {
        "source_session_id": "openhands",
        "target_session_id": "goal",
        "user_intent": "Adapt executor behavior.",
        "mount_mode": "reference",
        "create_adaptation_session": true,
        "make_active": false
      }
    },
    "rationale": "...",
    "warnings": ["..."]
  }
}
```

## Non-goals

The preview API must not:

```text
save the graph
call mount_session directly
allocate a worktree
start a workflow
call agent-core
call OpenHands or fallback executor
bypass session policy
```

## Why this exists

The main session graph and adapter engine already support direct graph mutation and semantic mounts. The preview API gives the prompt router and UI a safe planning surface so users can inspect proposed session topology changes before persistence.
