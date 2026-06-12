# Session graph options endpoint

`GET /api/session-graph/options` exposes the canonical enum values from `api.models.session_graph` for graph-native clients.

Frontend forms should consume this endpoint for session kinds, session statuses, edge types, event types, mount modes, projection selectors, adapter fields, policy visibility values, and action risk metadata.

This endpoint exists to prevent frontend drift. It intentionally excludes deprecated execution-session enums from `control-plane/sessions/models.py`.

## Client behavior

Clients should load this endpoint during graph UI startup. If the endpoint is temporarily unavailable during local development, clients may fall back to a complete copy of the current graph enum values, but the fallback is not authoritative.
