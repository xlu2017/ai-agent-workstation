"""Legacy compatibility module for session graph overview.

The overview endpoint is now implemented by the decomposed session graph router
under ``api.routes.session_graph.snapshot``. This module keeps the historical
``router`` symbol importable without registering a duplicate route.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/session-graph", tags=["session-graph"])

__all__ = ["router"]
