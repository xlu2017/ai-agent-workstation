# Session graph API

Base path: `/api/session-graph`

For control-plane rationale, see `docs/session-platform-intent.md`.

## Intent

The session graph API exposes the operational surface for durable session context. It should preserve the same semantics as the core session contracts: source identity is preserved, adapter interpretation is explicit, policy is validated before mutation, projections define execution context, and events preserve audit history.

The API is not generic graph CRUD. Mount, adapt, unmount, mapping update, event listing, projection lookup, and session-update application are separate operations because they have different validation, policy, and audit requirements.

## Endpoints

`GET /sessions`

Lists graph sessions visible to the caller.

`POST /sessions`

Creates a session record.

`GET /sessions/{session_id}`

Returns a single visible session.

`GET /edges?session_id=...`

Lists all visible edges or edges touching one session.

`POST /edges`

Creates an edge between visible sessions and appends a link event.

`POST /mount/preview`

Returns the edge, optional adapter session, adapter edges, projection, policy evidence, warnings, and events that would be produced by a mount. It does not persist changes.

`POST /mount`

Validates and persists the mount result.

`POST /unmount`

Removes a mounted relationship and appends an unmount event. Adapter-context edge cleanup is optional.

`POST /adapt`

Creates an adaptation session for a source and target.

`PUT /adapters/{adapter_session_id}/mappings`

Replaces or appends adapter mappings and records the mapping update as an event.

`GET /events`

Lists visible session events with optional filters.

`GET /context-projection/{session_id}`

Returns the latest projection for a session.

`POST /session-update/apply`

Applies a validated session update proposal.

`GET /snapshot`

Returns the scoped JSON-backed graph snapshot.

## Mount request

```json
{
  "source_session_id": "repo-reference",
  "target_session_id": "goal-integrate-reference",
  "user_intent": "Adapt executor behavior into platform.",
  "mount_mode": "reference",
  "create_adaptation_session": true,
  "make_active": false,
  "authorization": {
    "allow_private_projection": false,
    "authorized_by": "user",
    "reason": "explicitly approved projection",
    "grants": []
  }
}
```

## Mount result

A mount result includes:

- `mounted_edge`
- `adaptation_session`
- `adaptation_edges`
- `context_projection_delta`
- `policy_evidence`
- `warnings`
- `events`

`policy_evidence` records source and target effective policies, policy source IDs, authorization context, and individual policy checks.

`context_projection_delta` records projection mode, projection source, relevance score, evidence, include selectors, exclude selectors, budget, and rationale.

## Destructive mutation prevention

The mount endpoint rejects self-mounts, missing sessions, policy-blocked mounts, private cross-root projection without authorization, and graph cycles. It applies new edges/events instead of rewriting the source.

A semantically unusual mount should become a warning and a conservative projection when graph and policy constraints allow it. It should not become a destructive rewrite.

## Stack direction

The API is FastAPI/Pydantic-first. The local scaffold uses JSON persistence, but the intended production store is PostgreSQL 16+ with JSONB facets, adjacency tables, pgvector-backed memory chunks, and standard migrations. Hatchet workers can consume session events and run durable work, but Postgres remains the source of truth for sessions, edges, projections, locks, policies, and artifacts.
