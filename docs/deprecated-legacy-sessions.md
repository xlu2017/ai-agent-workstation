# Deprecated legacy sessions

Legacy session objects are deprecated without migration.

## Deprecated surfaces

The following old surfaces are intentionally closed:

```text
/api/sessions
/api/sessions/{...}
/api/v2/sessions/{...} timeline/event compatibility routes
control-plane/sessions/session_manager.py session.json storage
```

Calls to legacy HTTP routes return `410 Gone`. Calls to `session_manager.py` helpers raise `DeprecatedSessionStorageError`.

## Canonical session model

The canonical session model is now:

```text
api.models.session_graph.SessionRecord
api.services.session_graph_service.SessionGraphStore
/api/session-graph
```

Graph sessions own product identity, topology, parent/root relationships, mounts, adapter sessions, projections, policies, events, and workspace visibility.

## No migration policy

There is no automatic migration from `session.json` or `session-meta.json` into the session graph. Existing old objects are ignored by new product surfaces. New graph state must be created explicitly through the session graph API.

## Compatibility exception

`control-plane/sessions/models.py` remains importable for executor-internal compatibility only. Its `Session` and `SessionStore` are marked deprecated and must not be used as product-facing session identity.
