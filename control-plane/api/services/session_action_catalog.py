"""Canonical session-graph action catalog.

Session actions are graph mutations or graph previews. They are intentionally not
executed by the coding/runtime executor: their side effects are confined to the
session graph store and adapter engine.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.models.session_graph import (
    ActionRisk,
    ActionStakes,
    EdgeType,
    MountSessionRequest,
    SessionEdge,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
)
from api.services.session_adapter_engine import adapt_session, mount_session, preview_mount_session
from api.services.session_graph_service import SessionGraphStore, validate_graph_update


class SessionGraphActionDefinition(BaseModel):
    name: str
    title: str
    description: str
    domain: str = "session_graph"
    executor: str
    stakes: ActionStakes
    risk: ActionRisk
    preview_supported: bool = False
    side_effects: list[str] = Field(default_factory=list)
    params_schema: dict[str, Any] = Field(default_factory=dict)


class UnmountSessionActionParams(BaseModel):
    source_session_id: str
    target_session_id: str
    reason: str = "Unmount session from target context."
    remove_adapter_edges: bool = False


SESSION_ACTION_NAMES = {
    "session.mount",
    "session.mount.preview",
    "session.adapt",
    "session.unmount",
}


def session_action_catalog() -> dict[str, object]:
    """Return graph-native action definitions visible to planners and UI."""

    actions = [
        SessionGraphActionDefinition(
            name="session.mount",
            title="Mount session",
            description="Mount a source session under a target session, optionally creating an adapter session and context projection.",
            executor="session_graph.mount_session",
            stakes=ActionStakes.MODIFICATION,
            risk=ActionRisk.MEDIUM,
            preview_supported=True,
            side_effects=[
                "edge:mounted_under",
                "projection:context_delta",
                "event:session.mounted",
                "optional_session:adapter",
                "optional_edges:adapter",
            ],
            params_schema=MountSessionRequest.model_json_schema(),
        ),
        SessionGraphActionDefinition(
            name="session.mount.preview",
            title="Preview session mount",
            description="Validate and preview a mount without persisting graph changes.",
            executor="session_graph.preview_mount_session",
            stakes=ActionStakes.READ_ONLY,
            risk=ActionRisk.LOW,
            preview_supported=False,
            side_effects=[],
            params_schema=MountSessionRequest.model_json_schema(),
        ),
        SessionGraphActionDefinition(
            name="session.adapt",
            title="Create adapter session",
            description="Create an adapter session and projection scaffold between source and target sessions without mounting the source directly.",
            executor="session_graph.adapt_session",
            stakes=ActionStakes.MODIFICATION,
            risk=ActionRisk.MEDIUM,
            preview_supported=False,
            side_effects=[
                "session:adapter",
                "edges:adapter",
                "projection:context_delta",
                "event:session.adapter_created",
            ],
            params_schema=MountSessionRequest.model_json_schema(),
        ),
        SessionGraphActionDefinition(
            name="session.unmount",
            title="Unmount session",
            description="Remove a mounted_under edge between source and target sessions, optionally removing related adapter edges.",
            executor="session_graph.unmount_session",
            stakes=ActionStakes.MODIFICATION,
            risk=ActionRisk.MEDIUM,
            preview_supported=False,
            side_effects=["remove_edge:mounted_under", "event:session.unmounted"],
            params_schema=UnmountSessionActionParams.model_json_schema(),
        ),
    ]
    return {
        "catalog": "session_graph_actions",
        "canonical": True,
        "executor_scope": "session_graph",
        "actions": [action.model_dump(mode="json") for action in actions],
    }


def get_session_action(action_name: str) -> dict[str, object] | None:
    for action in session_action_catalog()["actions"]:  # type: ignore[index]
        if action["name"] == action_name:
            return action
    return None


def validate_session_action_params(action_name: str, params: dict[str, object]) -> dict[str, object]:
    """Validate action membership and parameter shape, but do not authorize execution."""

    if action_name not in SESSION_ACTION_NAMES:
        return {"ok": False, "error": f"Unknown session graph action: {action_name}"}
    try:
        if action_name in {"session.mount", "session.mount.preview", "session.adapt"}:
            MountSessionRequest.model_validate(params)
        elif action_name == "session.unmount":
            UnmountSessionActionParams.model_validate(params)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "action": get_session_action(action_name)}


def execute_session_action(
    store: SessionGraphStore,
    action_name: str,
    params: dict[str, object],
    *,
    preview: bool = False,
) -> dict[str, object]:
    """Execute a graph action through the session graph service layer."""

    validation = validate_session_action_params(action_name, params)
    if not validation["ok"]:
        raise ValueError(str(validation["error"]))

    if action_name in {"session.mount", "session.mount.preview"}:
        request = MountSessionRequest.model_validate(params)
        result = preview_mount_session(store, request) if preview or action_name == "session.mount.preview" else mount_session(store, request)
        return {
            "action_name": action_name,
            "preview": preview or action_name == "session.mount.preview",
            "result": result.model_dump(mode="json"),
        }

    if action_name == "session.adapt":
        request = MountSessionRequest.model_validate(params)
        session = adapt_session(store, request)
        return {
            "action_name": action_name,
            "preview": False,
            "result": {"session": session.model_dump(mode="json")},
        }

    if action_name == "session.unmount":
        body = UnmountSessionActionParams.model_validate(params)
        return {
            "action_name": action_name,
            "preview": False,
            "result": _unmount_session(store, body),
        }

    raise ValueError(f"Unsupported session graph action: {action_name}")


def _unmount_session(store: SessionGraphStore, body: UnmountSessionActionParams) -> dict[str, object]:
    graph = store.load()
    removed_edge_ids: list[str] = []
    retained_edges: list[SessionEdge] = []

    for edge in graph.edges:
        is_mount_edge = (
            edge.type == EdgeType.MOUNTED_UNDER
            and edge.source_session_id == body.source_session_id
            and edge.target_session_id == body.target_session_id
        )
        is_adapter_edge = body.remove_adapter_edges and edge.metadata.get("target_context_session_id") == body.target_session_id
        if is_mount_edge or is_adapter_edge:
            removed_edge_ids.append(edge.id)
        else:
            retained_edges.append(edge)

    if not removed_edge_ids:
        raise ValueError("No mounted edge found for source and target sessions.")

    graph.edges = retained_edges
    event = SessionEvent(
        type=SessionEventType.SESSION_UNMOUNTED,
        session_id=body.target_session_id,
        actor=SessionEventActor.SYSTEM,
        data={
            "source_session_id": body.source_session_id,
            "target_session_id": body.target_session_id,
            "removed_edge_ids": removed_edge_ids,
            "reason": body.reason,
            "remove_adapter_edges": body.remove_adapter_edges,
            "source": "session_action_catalog",
        },
    )
    graph.events.append(event)
    issues = validate_graph_update(graph)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(graph)
    return {"removed_edge_ids": removed_edge_ids, "event": event.model_dump(mode="json")}
