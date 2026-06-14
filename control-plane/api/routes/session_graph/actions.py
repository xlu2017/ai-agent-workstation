"""Session graph canonical action routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import EdgeType, SessionEdge, SessionEvent, SessionEventActor, SessionEventType, SessionKind
from api.routes.session_graph.helpers import RequestContext, _context, _get_visible_session, _store
from api.services.session_graph_service import SessionGraphStore, validate_graph_update

router = APIRouter()


class SessionActionRequest(BaseModel):
    action_name: str
    params: dict[str, object] = Field(default_factory=dict)
    preview: bool = False


class MountParams(BaseModel):
    source_session_id: str
    target_session_id: str
    user_intent: str = "Attach source context to target session."
    mount_mode: str = "reference"
    create_adaptation_session: bool = False
    make_active: bool = False


@router.get("/actions")
def list_session_graph_actions() -> dict[str, object]:
    return {"catalog": "session_graph_actions", "canonical": True, "actions": [{"name": "session.mount", "preview_supported": True}, {"name": "session.mount.preview", "preview_supported": False}]}


@router.get("/actions/{action_name}")
def get_session_graph_action(action_name: str) -> dict[str, object]:
    for action in list_session_graph_actions()["actions"]:  # type: ignore[index]
        if action["name"] == action_name:
            return {"action": action}
    raise HTTPException(404, f"Unknown session graph action: {action_name}")


@router.post("/actions/validate")
def validate_session_graph_action(body: SessionActionRequest) -> dict[str, object]:
    return _validate_action_params(body.action_name, body.params)


@router.post("/actions/apply")
def apply_session_graph_action(body: SessionActionRequest, context: RequestContext = Depends(_context)) -> dict[str, object]:
    if body.action_name not in {"session.mount", "session.mount.preview"}:
        raise HTTPException(400, f"Unknown session graph action: {body.action_name}")
    params = MountParams.model_validate(body.params)
    store = _store()
    _get_visible_session(store, params.source_session_id, context)
    _get_visible_session(store, params.target_session_id, context)
    try:
        result = _preview_mount(store, params) if body.preview or body.action_name == "session.mount.preview" else _mount(store, params)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"action_name": body.action_name, "preview": body.preview or body.action_name == "session.mount.preview", "result": result}


def _validate_action_params(action_name: str, params: dict[str, object]) -> dict[str, object]:
    if action_name not in {"session.mount", "session.mount.preview"}:
        return {"ok": False, "error": f"Unknown session graph action: {action_name}"}
    try:
        MountParams.model_validate(params)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _session_pair(store: SessionGraphStore, body: MountParams):
    graph = store.load()
    source = next((session for session in graph.sessions if session.id == body.source_session_id), None)
    target = next((session for session in graph.sessions if session.id == body.target_session_id), None)
    if source is None:
        raise ValueError(f"Source session {body.source_session_id} not found.")
    if target is None:
        raise ValueError(f"Target session {body.target_session_id} not found.")
    if source.id == target.id:
        raise ValueError("A session cannot be mounted under itself.")
    return graph, source, target


def _preview_mount(store: SessionGraphStore, body: MountParams) -> dict[str, object]:
    graph, source, target = _session_pair(store, body)
    duplicate = any(edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == source.id and edge.target_session_id == target.id for edge in graph.edges)
    return {"ok": not duplicate, "source_session_id": source.id, "target_session_id": target.id, "duplicate": duplicate}


def _mount(store: SessionGraphStore, body: MountParams) -> dict[str, object]:
    graph, source, target = _session_pair(store, body)
    if any(edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == source.id and edge.target_session_id == target.id for edge in graph.edges):
        raise ValueError(f"Duplicate mounted_under edge {source.id} -> {target.id}.")
    edge = SessionEdge(type=EdgeType.MOUNTED_UNDER, source_session_id=source.id, target_session_id=target.id, metadata={"reason": body.user_intent, "mount_mode": body.mount_mode})
    graph.edges.append(edge)
    if body.make_active:
        for idx, session in enumerate(graph.sessions):
            if session.id == target.id:
                metadata = dict(session.metadata)
                metadata["active_context_session_id"] = source.id
                if source.kind == SessionKind.REPO:
                    metadata["repo_session_id"] = source.id
                    repo = source.facets.get("repo", {})
                    if isinstance(repo, dict) and isinstance(repo.get("path"), str):
                        metadata["repo_path"] = repo["path"]
                    if isinstance(repo, dict) and isinstance(repo.get("full_name"), str):
                        metadata["repo_id"] = repo["full_name"]
                session.metadata = metadata
                graph.sessions[idx] = session
                break
    event = SessionEvent(type=SessionEventType.SESSION_MOUNTED, session_id=target.id, actor=SessionEventActor.SYSTEM, data={"source_session_id": source.id, "target_session_id": target.id, "edge_id": edge.id, "make_active": body.make_active})
    graph.events.append(event)
    issues = validate_graph_update(graph)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(graph)
    return {"edge": edge.model_dump(mode="json"), "event": event.model_dump(mode="json")}
