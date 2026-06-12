"""Session graph schema options for frontend forms.

This endpoint is the graph-native replacement for hardcoded session/edge enum
lists in frontend components. It deliberately exposes only canonical graph model
values and does not include deprecated execution-session enums.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter

from api.models.session_graph import (
    ActionRisk,
    ActionStakes,
    AdaptationMode,
    AdapterMappingItemStatus,
    AdapterMappingStatus,
    AdapterRelationship,
    AdapterSourceRole,
    AdapterTargetRole,
    EdgeType,
    MountMode,
    PolicyVisibility,
    PreservationMode,
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
        "mount_modes": _values(MountMode),
        "projection_modes": _values(ProjectionMode),
        "projection_sources": _values(ProjectionSource),
        "projection_selectors": _values(ProjectionSelector),
        "policy_visibilities": _values(PolicyVisibility),
        "adapter_source_roles": _values(AdapterSourceRole),
        "adapter_target_roles": _values(AdapterTargetRole),
        "preservation_modes": _values(PreservationMode),
        "adaptation_modes": _values(AdaptationMode),
        "adapter_mapping_statuses": _values(AdapterMappingStatus),
        "adapter_relationships": _values(AdapterRelationship),
        "adapter_mapping_item_statuses": _values(AdapterMappingItemStatus),
        "session_update_classifications": _values(SessionUpdateClassification),
        "action_stakes": _values(ActionStakes),
        "action_risks": _values(ActionRisk),
    }
