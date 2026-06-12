"""Platform app discovery route."""

from fastapi import APIRouter, Query

from api.services.platform_apps import discover_popular_applications

router = APIRouter(tags=["platform-apps"])


@router.get("/api/session-graph/platform-apps")
def list_platform_apps(q: str = Query("")) -> dict[str, list[dict[str, object]]]:
    return {"applications": discover_popular_applications(q)}
