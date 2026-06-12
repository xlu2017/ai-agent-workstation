"""Deprecated v2 execution-session routes.

The old ``/api/v2/sessions`` route family used deprecated execution-session
objects. It is intentionally closed instead of migrated. Use
``/api/session-graph`` for canonical sessions and graph events.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v2", tags=["deprecated-v2-sessions"])

DEPRECATION_DETAIL = {
    "error": "legacy_v2_sessions_deprecated",
    "message": "Legacy /api/v2/sessions endpoints are deprecated and intentionally not migrated.",
    "replacement": "/api/session-graph",
    "migration": "not_supported",
}


def set_controller(ctrl: object) -> None:
    raise RuntimeError(DEPRECATION_DETAIL["message"])


def _gone(path: str = "") -> None:
    detail = dict(DEPRECATION_DETAIL)
    detail["path"] = f"/api/v2/sessions/{path}" if path else "/api/v2/sessions"
    raise HTTPException(status_code=410, detail=detail)


@router.api_route(
    "/sessions",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
def deprecated_v2_sessions_root() -> None:
    _gone()


@router.api_route(
    "/sessions/{legacy_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
def deprecated_v2_sessions_path(legacy_path: str) -> None:
    _gone(legacy_path)
