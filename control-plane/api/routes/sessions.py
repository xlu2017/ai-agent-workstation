"""Deprecated legacy session routes.

The old ``/api/sessions`` surface used ``session.json`` runtime objects and is
now intentionally closed. Do not migrate old objects into the new model. New
code must use the session graph API under ``/api/session-graph`` and represent
runtime concerns as graph facets or explicit graph relationships.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["deprecated-sessions"])

DEPRECATION_DETAIL = {
    "error": "legacy_sessions_deprecated",
    "message": "Legacy /api/sessions endpoints are deprecated and intentionally not migrated.",
    "replacement": "/api/session-graph",
    "migration": "not_supported",
}


def _raise_legacy_sessions_gone(path: str = "") -> None:
    detail = dict(DEPRECATION_DETAIL)
    if path:
        detail["path"] = f"/api/sessions/{path}"
    else:
        detail["path"] = "/api/sessions"
    raise HTTPException(status_code=410, detail=detail)


@router.api_route(
    "/api/sessions",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
def deprecated_legacy_sessions_root() -> None:
    """Return 410 for the removed legacy session collection endpoint."""

    _raise_legacy_sessions_gone()


@router.api_route(
    "/api/sessions/{legacy_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
def deprecated_legacy_sessions_path(legacy_path: str) -> None:
    """Return 410 for all removed legacy session member/action endpoints."""

    _raise_legacy_sessions_gone(legacy_path)
