"""Session graph schema options for frontend forms.

This endpoint exposes only the canonical graph model values that are still owned
by the current session graph model. Deprecated adapter-engine enums are not part
of this route.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter

from api.models.session_graph import (
    EdgeType,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
    SessionEventActor,
    SessionEventType,
    SessionFacetName,
    SessionKind,
    SessionStatus,
    SessionUpdateClassification,
)

router = APIRouter()


def _values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


@router.get("/options")
def get_session_graph_options() -> dict[str, list[str]]:
    """Return canonical enum values used by graph-native clients."""

    return {
        "session_kinds": _values(SessionKind),
        "session_statuses": _values(SessionStatus),
        "session_facets": _values(SessionFacetName),
        "edge_types": _values(EdgeType),
        "event_types": _values(SessionEventType),
        "event_actors": _values(SessionEventActor),
        "projection_modes": _values(ProjectionMode),
        "projection_sources": _values(ProjectionSource),
        "projection_selectors": _values(ProjectionSelector),
        "session_update_classifications": _values(SessionUpdateClassification),
    }
