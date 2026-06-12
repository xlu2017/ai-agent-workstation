# Multi Frontend End-to-End Implementation

## What is now end-to-end

The dedicated multi-frontend API is mounted in `control-plane/api/server.py` and is the primary runtime path:

```text
web panel -> /api/multi-frontend/* -> MultiFrontendSessionController -> session graph
```

The web panel still keeps a defensive fallback path through the already-mounted session graph CRUD routes:

```text
web panel -> /api/session-graph/sessions and /api/session-graph/edges -> session graph
```

The fallback is retained for development environments that have not restarted onto the latest server code, but it is no longer the intended primary path.

## User workflow

```text
open the workstation UI
click Multi-frontend
enter app title and backend URL
create demo topology
view frontend matrix
register demo trace
refresh matrix
```

The created topology contains:

```text
root app session
shared backend runtime session
Chrome desktop frontend runtime session
Android emulator frontend runtime session
iOS simulator frontend runtime session
parent_id containment from app to backend/frontends
depends_on edges from each frontend to backend
multi_frontend_topology state on the root app session
```

## Files added for the end-to-end path

```text
control-plane/api/multi_frontend.py
control-plane/api/models/multi_frontend.py
control-plane/api/services/multi_frontend_session_controller.py
control-plane/web/src/multi-frontend-panel.ts
control-plane/web/src/multi-frontend-panel.css
control-plane/tests/test_multi_frontend_api_router.py
```

`control-plane/web/src/main.tsx` imports the panel and CSS so the feature appears in the existing app bundle. `control-plane/api/server.py` imports and includes the multi-frontend router so `/api/multi-frontend/*` is live after the server restarts.

## Dedicated API status

Mounted in `control-plane/api/server.py`:

```python
from api.multi_frontend import router as multi_frontend_router
app.include_router(multi_frontend_router)
```

## Why the fallback remains acceptable

The source of truth is the session graph. The fallback writes the same graph shape as the controller:

```text
SessionRecord(kind=app, state.multi_frontend_topology)
SessionRecord(kind=runtime, role=backend, parent_id=root_app_session)
SessionRecord(kind=runtime, role=frontend_client, parent_id=root_app_session)
SessionEdge(type=depends_on, frontend -> backend)
```

That means the fallback does not create a divergent schema or require data migration.

## Verification

```bash
cd control-plane/web
npm run build

cd ..
pytest tests/test_multi_frontend_session_controller.py -q
pytest tests/test_multi_frontend_api_router.py -q
python -m py_compile api/server.py api/multi_frontend.py api/services/multi_frontend_session_controller.py
```
