#!/usr/bin/env python3
"""
Control Plane API — FastAPI server.

Large route files are intentionally split into small, domain-specific router
modules so future agents can safely make whole-file replacement edits to
isolated route domains without risking unrelated route logic.

Route modules live under ``api/routes/`` (top-level API routes) and
``api/routes/session_graph/`` (session graph sub-routes).  This entrypoint
only composes routers and sets up middleware.
"""

import sys
from pathlib import Path

# Add control-plane root and CLI to path for imports
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(CONTROL_PLANE_ROOT / "cli"))
sys.path.insert(0, str(CONTROL_PLANE_ROOT / "core"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.health import router as health_router
from api.routes.remote_desktop import router as remote_desktop_router
from api.routes.sessions import router as sessions_router
from api.routes.session_events import router as session_events_router
from api.routes.repo_provider import router as repo_provider_router
from api.routes.repo_sources import router as repo_sources_router
from api.routes.services import router as services_router
from api.service_update_check import router as service_update_check_router
from api.routes.app_automation import router as app_automation_router
from api.routes.visual_automation import router as visual_automation_router
from api.routes.models import router as models_router
from api.routes.knowledge import router as knowledge_router
from api.routes.filesystem import router as filesystem_router
from api.routes.multi_frontend import router as multi_frontend_router
from api.routes.ui_capabilities import router as ui_capabilities_router
from api.routes.session_graph.router import router as session_graph_router

app = FastAPI(title="Workstation Control Plane", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Router composition ---
app.include_router(health_router)
app.include_router(remote_desktop_router)
app.include_router(sessions_router)
app.include_router(session_events_router)
app.include_router(repo_provider_router)
app.include_router(repo_sources_router)
app.include_router(services_router)
app.include_router(service_update_check_router)
app.include_router(app_automation_router)
app.include_router(visual_automation_router)
app.include_router(models_router)
app.include_router(knowledge_router)
app.include_router(filesystem_router)
app.include_router(ui_capabilities_router)
app.include_router(session_graph_router)
app.include_router(multi_frontend_router)
