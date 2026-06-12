"""Composite session graph router."""

from fastapi import APIRouter

from api.routes.session_graph.adapters import router as adapters_router
from api.routes.session_graph.dev_workflow import router as dev_workflow_router
from api.routes.session_graph.edges import router as edges_router
from api.routes.session_graph.events import router as events_router
from api.routes.session_graph.options import router as options_router
from api.routes.session_graph.platform_apps import router as platform_apps_router
from api.routes.session_graph.projections import router as projections_router
from api.routes.session_graph.sessions import router as sessions_router
from api.routes.session_graph.settings import router as settings_router
from api.routes.session_graph.snapshot import router as snapshot_router

router = APIRouter(prefix="/api/session-graph", tags=["session-graph"])

router.include_router(sessions_router)
router.include_router(edges_router)
router.include_router(projections_router)
router.include_router(adapters_router)
router.include_router(events_router)
router.include_router(settings_router)
router.include_router(platform_apps_router)
router.include_router(snapshot_router)
router.include_router(options_router)
router.include_router(dev_workflow_router)
