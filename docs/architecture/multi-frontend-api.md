# Multi Frontend API

## Files

```text
control-plane/api/models/multi_frontend.py
control-plane/api/services/multi_frontend_session_controller.py
control-plane/api/multi_frontend.py
control-plane/api/server.py
control-plane/tests/test_multi_frontend_session_controller.py
control-plane/tests/test_multi_frontend_api_router.py
```

## API endpoints

The router lives in `control-plane/api/multi_frontend.py` and is mounted by `control-plane/api/server.py`.

```text
POST /api/multi-frontend/topologies
GET  /api/multi-frontend/topologies/{root_session_id}
GET  /api/multi-frontend/topologies/{root_session_id}/matrix
GET  /api/multi-frontend/topologies/{root_session_id}/frontends/{frontend_instance_id}/trace-headers
POST /api/multi-frontend/traces
```

## Mounting

Mounted in `control-plane/api/server.py`:

```python
from api.multi_frontend import router as multi_frontend_router
app.include_router(multi_frontend_router)
```

The web panel keeps a defensive current-server fallback path using session graph CRUD routes, but the mounted `/api/multi-frontend/*` route family is now the intended primary path.

## Controller responsibilities

`MultiFrontendSessionController` does the following:

```text
creates root APP session
creates shared backend RUNTIME session
creates one frontend RUNTIME session per client
uses parent_id for app-to-runtime containment
adds depends_on edges from each frontend to backend
stores multi_frontend_topology on root app session state
generates trace correlation headers
registers cross-client traces
returns frontend matrix rows for UI rendering
```

Containment is represented with `parent_id` because the existing graph validator derives containment edges from parent pointers. Explicit graph edges are reserved for cross-session dependencies.

## Trace headers

Each frontend request to the backend should include:

```text
x-agent-root-session-id
x-agent-backend-session-id
x-agent-frontend-session-id
x-agent-frontend-instance-id
x-agent-device-profile-id
x-agent-user-flow-id
x-agent-trace-id
```

These headers let the platform connect a UI action in one client to backend route logs and traces.
