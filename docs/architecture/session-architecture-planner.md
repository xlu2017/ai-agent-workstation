# Session Architecture Planner

## Intent

The sessions architecture treats every durable unit of work or context as a session:

- repo sessions
- app sessions
- goal sessions
- work sessions
- question sessions
- validation sessions
- adapter sessions
- runtime sessions
- memory sessions
- artifact sessions
- container sessions

The control plane must support moving or mounting any session under any other session without semantic loss. A broad repo session can be mounted under a tiny goal session, and a focused work session can be mounted under an app session, without rewriting the source session identity, history, policy, or facets.

The new planner scaffold converts high-level session architecture intent into deterministic `SessionUpdateProposal` objects. It does not execute graph changes. Execution remains with `SessionGraphStore.apply_update_proposal` and the session adapter engine.

## Files

```text
control-plane/api/services/session_architecture_planner.py
control-plane/tests/test_session_architecture_planner.py
```

## Boundary

The planner owns proposal construction only:

```text
user/session-router intent
→ SessionArchitecturePlan
→ SessionUpdateProposal or MountSessionRequest
```

It must not:

```text
persist session graph state
allocate worktrees
start workflows
call agent-core
call executors
perform mounts directly
perform adaptation directly
bypass policy checks
```

The existing adapter engine still owns semantic mount execution:

```text
SessionUpdateProposal.mount_request
→ session_adapter_engine.mount_session
→ mounted edge
→ optional adapter session
→ adapter edges
→ context projection
→ policy evidence
→ events
```

## Planner functions

### `build_session_record`

Creates a proposed `SessionRecord` from a `SessionSeed` without persistence.

Use for root, child, sibling, goal, work, repo, and adapter planning paths.

### `plan_create_root`

Creates a root session proposal.

Example use:

```text
Create a repo session for a newly connected repository.
```

### `plan_create_child`

Creates a child session under a known parent and emits a containment edge.

Example use:

```text
Current app session → child goal session → child work session.
```

### `plan_create_sibling`

Creates a sibling in the same root context and emits a `sibling_of` edge.

Example use:

```text
User starts a separate docs cleanup while an auth fix is running.
```

### `plan_move_under`

Proposes a non-destructive semantic move from source to target.

For unlike session kinds, broad-source-to-focused-target moves, or long user intent, it sets `create_adaptation_session=true` so the adapter engine can preserve source identity and create a projection.

Example use:

```text
Move the OpenHands repo session under the goal session “integrate OpenHands executor behavior”.
```

This should not rewrite `source.parent_id`. It should create a mount/adaptation request.

### `plan_question_only`

Creates a no-graph-change proposal for read-only explanation or Q&A.

### `propose_context_sources`

Deterministically ranks candidate sessions for future context projection. This is placeholder logic for the future retrieval-backed context router.

## Example flow

```text
1. User says: “Move OpenHands under this integration goal.”
2. Prompt router classifies the intent as move_under.
3. SessionArchitecturePlanner creates a SessionUpdateProposal with a MountSessionRequest.
4. API/controller calls SessionGraphStore.apply_update_proposal.
5. SessionGraphStore delegates mount execution to session_adapter_engine.mount_session.
6. Adapter engine validates policy, creates mounted/adapted edges, creates adapter session if needed, and creates context projection.
7. UI renders the mounted source, adapter session, warnings, and projection evidence.
```

## Design invariants

```text
A session move is not a destructive parent rewrite.
A session mount preserves source identity.
A cross-kind or ambiguous move requires adapter interpretation.
A broad session mounted under a focused session gets a bounded projection.
Policy evidence must stay visible.
The planner proposes; the graph store and adapter engine persist.
```

## Next integration step

Wire the planner into the existing `/api/session-graph/session-update/apply` path by adding a route that accepts a compact intent request and returns `SessionArchitecturePlan`. That route should stay preview-first and should require a separate apply call for persistence.
