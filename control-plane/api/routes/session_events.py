"""Deprecated legacy session event routes.

The old session event readers consumed filesystem session state. That state model
is deprecated without migration. Use session graph events under
``/api/session-graph/events`` instead.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["deprecated-session-events"])

DEPRECATION_DETAIL = {
    "error": "legacy_session_events_deprecated",
    "message": "Legacy session event and timeline endpoints are deprecated and intentionally not migrated.",
    "replacement": "/api/session-graph/events",
    "migration": "not_supported",
}


def _gone(path: str) -> None:
    detail = dict(DEPRECATION_DETAIL)
    detail["path"] = path
    raise HTTPException(status_code=410, detail=detail)


@router.api_route(
    "/api/v2/sessions/{legacy_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
def deprecated_v2_session_path(legacy_path: str) -> None:
    _gone(f"/api/v2/sessions/{legacy_path}")
