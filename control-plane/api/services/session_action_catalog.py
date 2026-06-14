"""Graph-native session action catalog.

These actions mutate only the session graph. They do not import or execute the
deprecated adapter engine.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.models.session_graph import EdgeType, SessionEdge, SessionEvent, SessionEventActor, SessionEventType, SessionKind
from api.services.session_graph_service import SessionGraphStore, validate_graph_update


class MountSessionRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    user_intent: str = "Attach source context to target session."
    mount_mode: str = "reference"
    create_adaptation_session: bool = False
    make_active: bool = False


class UnmountSessionActionParams(BaseModel):
    source_session_id: str
    target_session_id: str
    reason: str = "Detach source context from target session."


ACTION_NAMES = {"session.mount", "session.mount.preview", "session.unmount"}


def session_action_catalog() -> dict[str, object]:
    return {
        "catalog": "session_graph_actions",
        "canonical": True,
        "executor_scope": "session_graph",
        "actions": [
            {"name": "session.mount", "executor": "session_graph.mount_session", "preview_supported": True, "params_schema": MountSessionRequest.model_json_schema()},
            {"name": "session.mount.preview", "executor": "session_graph.preview_mount_session", "preview_supported": False, "params_schema": MountSessionRequest.model_json_schema()},
            {"name": "session.unmount", "executor": "session_graph.unmount_session", "preview_supported": False, "params_schema": UnmountSessionActionParams.model_json_schema()},
        ],
    }


def get_session_action(action_name: str) -> dict[str, object] | None:
    for action in session_action_catalog()["actions"]:  # type: ignore[index]
        if action["name"] == action_name:
            return action
    return None


def validate_session_action_params(action_name: str, params: dict[str, object]) -> dict[str, object]:
    if action_name not in ACTION_NAMES:
        return {"ok": False, "error": f"Unknown session graph action: {action_name}"}
    try:
        MountSessionRequest.model_validate(params) if action_name != "session.unmount" else UnmountSessionActionParams.model_validate(params)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "action": get_session_action(action_name)}


def execute_session_action(store: SessionGraphStore, action_name: str, params: dict[str, object], *, preview: bool = False) -> dict[str, object]:
    validation = validate_session_action_params(action_name, params)
    if not validation["ok"]:
        raise ValueError(str(validation["error"]))
    if action_name in {"session.mount", "session.mount.preview"}:
        request = MountSessionRequest.model_validate(params)
        is_preview = preview or action_name == "session.mount.preview"
        result = _preview_mount(store, request) if is_preview else _mount(store, request)
        return {"action_name": action_name, "preview": is_preview, "result": result}
    request = UnmountSessionActionParams.model_validate(params)
    return {"action_name": action_name, "preview": False, "result": _unmount(store, request)}


def _pair(store: SessionGraphStore, request: MountSessionRequest):
    graph = store.load()
    source = next((session for session in graph.sessions if session.id == request.source_session_id), None)
    target = next((session for session in graph.sessions if session.id == request.target_session_id), None)
    if source is None:
        raise ValueError(f"Source session {request.source_session_id} not found.")
    if target is None:
        raise ValueError(f"Target session {request.target_session_id} not found.")
    if source.id == target.id:
        raise ValueError("A session cannot be mounted under itself.")
    return graph, source, target


def _preview_mount(store: SessionGraphStore, request: MountSessionRequest) -> dict[str, object]:
    graph, source, target = _pair(store, request)
    duplicate = any(edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == source.id and edge.target_session_id == target.id for edge in graph.edges)
    return {"ok": not duplicate, "source_session_id": source.id, "target_session_id": target.id, "duplicate": duplicate}


def _mount(store: SessionGraphStore, request: MountSessionRequest) -> dict[str, object]:
    graph, source, target = _pair(store, request)
    if any(edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == source.id and edge.target_session_id == target.id for edge in graph.edges):
        raise ValueError(f"Duplicate mounted_under edge {source.id} -> {target.id}.")
    edge = SessionEdge(type=EdgeType.MOUNTED_UNDER, source_session_id=source.id, target_session_id=target.id, metadata={"reason": request.user_intent, "mount_mode": request.mount_mode})
    graph.edges.append(edge)
    if request.make_active:
        for idx, session in enumerate(graph.sessions):
            if session.id == target.id:
                metadata = dict(session.metadata)
                metadata["active_context_session_id"] = source.id
                if source.kind == SessionKind.REPO:
                    metadata["repo_session_id"] = source.id
                session.metadata = metadata
                graph.sessions[idx] = session
                break
    event = SessionEvent(type=SessionEventType.SESSION_MOUNTED, session_id=target.id, actor=SessionEventActor.SYSTEM, data={"source_session_id": source.id, "target_session_id": target.id, "edge_id": edge.id})
    graph.events.append(event)
    issues = validate_graph_update(graph)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(graph)
    return {"edge": edge.model_dump(mode="json"), "event": event.model_dump(mode="json")}


def _unmount(store: SessionGraphStore, request: UnmountSessionActionParams) -> dict[str, object]:
    graph = store.load()
    removed_ids = [edge.id for edge in graph.edges if edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == request.source_session_id and edge.target_session_id == request.target_session_id]
    if not removed_ids:
        raise ValueError("No mounted edge found for source and target sessions.")
    graph.edges = [edge for edge in graph.edges if edge.id not in removed_ids]
    event = SessionEvent(type=SessionEventType.SESSION_UNMOUNTED, session_id=request.target_session_id, actor=SessionEventActor.SYSTEM, data={"removed_edge_ids": removed_ids, "reason": request.reason})
    graph.events.append(event)
    issues = validate_graph_update(graph)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(graph)
    return {"removed_edge_ids": removed_ids, "event": event.model_dump(mode="json")}
