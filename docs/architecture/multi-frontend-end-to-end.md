# Multi Frontend End-to-End Implementation

## What is now end-to-end

The implementation has two working paths:

```text
Preferred API path
  web panel -> /api/multi-frontend/* -> MultiFrontendSessionController -> session graph

Current-server fallback path
  web panel -> /api/session-graph/sessions and /api/session-graph/edges -> session graph
```

The fallback path exists because the current control-plane server already mounts the session graph router. It lets the UI create and render a topology without waiting for a full edit of the large server module.

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
control-plane/web/src/multi-frontend-panel.ts
control-plane/web/src/multi-frontend-panel.css
control-plane/tests/test_multi_frontend_api_router.py
```

`control-plane/web/src/main.tsx` imports the panel and CSS so the feature appears in the existing app bundle.

## Dedicated API status

The dedicated API router exists:

```text
control-plane/api/multi_frontend.py
```

It should eventually be mounted directly in `control-plane/api/server.py`:

```python
from api.multi_frontend import router as multi_frontend_router
app.include_router(multi_frontend_router)
```

Until that direct mount is applied, the UI still works by using generic session graph CRUD endpoints.

## Why this fallback is acceptable

The source of truth is the session graph. The fallback writes the same graph shape as the controller:

```text
SessionRecord(kind=app, state.multi_frontend_topology)
SessionRecord(kind=runtime, role=backend, parent_id=root_app_session)
SessionRecord(kind=runtime, role=frontend_client, parent_id=root_app_session)
SessionEdge(type=depends_on, frontend -> backend)
```

That means a later server mount does not require data migration.

## Verification

```bash
cd control-plane/web
npm run build

cd ..
pytest tests/test_multi_frontend_session_controller.py -q
pytest tests/test_multi_frontend_api_router.py -q
```
