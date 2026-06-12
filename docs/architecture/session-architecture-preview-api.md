# Session Architecture Preview and Apply API

## Intent

`control-plane/api/session_architecture.py` provides a router for session architecture changes. It exposes deterministic planning endpoints that return a `SessionArchitecturePlan` and matching apply endpoints that persist the proposal through the existing session graph store.

The API keeps preview and apply separate:

```text
preview session architecture proposal
→ inspect returned SessionUpdateProposal or MountSessionRequest
→ apply the same operation through /api/session-architecture/apply/*
→ SessionGraphStore.apply_update_proposal persists the graph change
```

This keeps the planner from becoming an execution or authorization layer. The planner still proposes. The graph store and adapter engine still persist and enforce structural constraints.

## Router

```text
prefix: /api/session-architecture
tag: session-architecture
```

The router is implemented in `control-plane/api/session_architecture.py`. It should be mounted in `control-plane/api/server.py` before it is available from the running FastAPI app:

```python
from api.session_architecture import router as session_architecture_router

app.include_router(session_architecture_router)
```

## Scope headers

The router accepts the same lightweight workspace headers used by the session graph API:

```text
X-Workspace-Id: workspace id, defaults to default
X-User-Id: optional user id for private session visibility
```

Created sessions are stamped with `workspace_id` and, when provided, `owner_user_id`. Existing source, target, parent, and active sessions are checked for workspace/private visibility before preview or apply.

## Preview endpoints

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

## Apply endpoints

Apply endpoints construct the same proposal as their preview counterpart and then call `SessionGraphStore.apply_update_proposal`.

```text
POST /api/session-architecture/apply/create-root
POST /api/session-architecture/apply/create-child
POST /api/session-architecture/apply/create-sibling
POST /api/session-architecture/apply/move-under
POST /api/session-architecture/apply/question-only
```

Apply responses include both the planner output and the updated graph snapshot:

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
  },
  "graph": {
    "sessions": [],
    "edges": [],
    "events": [],
    "projections": []
  }
}
```

## Non-goals

The architecture API must not:

```text
allocate a worktree
start a workflow
call agent-core
call OpenHands or fallback executor
execute code
commit, push, deploy, or mutate repo files
bypass graph validation or session policy
```

## Why this exists

The main session graph and adapter engine already support graph mutation and semantic mounts. This API gives the prompt router and UI a safe planning surface and a focused persistence surface for topology changes.

The core invariant remains:

```text
Planner proposes.
Graph store persists.
Adapter engine projects.
Executors do not participate in topology changes.
```
