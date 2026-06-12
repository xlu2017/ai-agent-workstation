"""Session graph — platform app discovery route (scoped under /api/session-graph)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.services.platform_apps import discover_popular_applications

router = APIRouter()


@router.get("/platform-apps")
def list_platform_apps(q: str = Query("")) -> dict[str, list[dict[str, object]]]:
    return {"applications": discover_popular_applications(q)}
