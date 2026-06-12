# Session graph overview endpoint

`GET /api/session-graph/overview` returns scoped aggregate counts for the session graph without fetching the full snapshot.

The endpoint is implemented in `control-plane/api/session_graph_overview.py` and is covered by `control-plane/tests/test_session_graph_overview.py`.

## Response shape

```json
{
  "sessions": {
    "total": 3,
    "by_kind": { "repo": 1, "goal": 1, "adapter": 1 },
    "by_status": { "proposed": 3 },
    "roots": 3
  },
  "edges": {
    "total": 3,
    "by_type": { "mounted_under": 1, "adapts_from": 1, "adapts_into": 1 }
  },
  "events": {
    "total": 5,
    "latest": {}
  },
  "projections": {
    "total": 1,
    "total_budget": {
      "max_tokens": 4000,
      "max_files": 12,
      "max_events": 50
    }
  }
}
```

## Scope behavior

The endpoint uses the same lightweight workspace headers as the session graph API:

```text
X-Workspace-Id
X-User-Id
```

Counts only include sessions visible to the caller, edges where both endpoints are visible, events attached to visible sessions, and projections attached to visible active/source sessions.

## Intended use

Use this endpoint for settings pages, dashboards, CLI checks, and health panels that need a fast graph overview rather than the complete `/api/session-graph/snapshot` payload.
