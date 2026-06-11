# Session graph API

Base path: `/api/session-graph`

## Endpoints

`GET /sessions`

Lists graph sessions.

`POST /sessions`

Creates a session record.

`GET /sessions/{session_id}`

Returns a single session.

`GET /edges?session_id=...`

Lists all edges or edges touching one session.

`POST /mount/preview`

Returns the edge, optional adapter session, adapter edges, projection, warnings,
and events that would be produced by a mount. It does not persist changes.

`POST /mount`

Validates and persists the mount result.

`POST /adapt`

Creates an adaptation session for a source and target.

`GET /context-projection/{session_id}`

Returns the latest projection for a session.

`POST /session-update/apply`

Applies a validated session update proposal.

`GET /snapshot`

Returns the full JSON-backed graph snapshot.

## Mount request

```json
{
  "source_session_id": "repo-openhands",
  "target_session_id": "goal-integrate-openhands",
  "user_intent": "Adapt executor behavior into platform.",
  "mount_mode": "reference",
  "create_adaptation_session": true,
  "make_active": false
}
```

## Destructive mutation prevention

The mount endpoint rejects self-mounts, missing sessions, policy-blocked mounts,
and graph cycles. It applies new edges/events instead of rewriting the source.

## Stack direction

The API is FastAPI/Pydantic-first. The local scaffold uses JSON persistence, but
the intended production store is PostgreSQL 16+ with JSONB facets, adjacency
tables, pgvector-backed memory chunks, and standard migrations. Hatchet workers
can consume session events and run durable work, but Postgres remains the source
of truth for sessions, edges, projections, locks, policies, and artifacts.
