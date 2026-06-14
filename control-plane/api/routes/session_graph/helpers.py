"""Shared helpers for session graph sub-routers."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from api.models.session_graph import (
    ContextProjection,
    SessionEdge,
    SessionEvent,
    SessionEventActor,
    SessionGraphSnapshot,
    SessionRecord,
    utc_now,
)
from api.services.session_graph_service import SessionGraphStore, validate_graph_update


class RequestContext(BaseModel):
    workspace_id: str = "default"
    user_id: str | None = None


def _store() -> SessionGraphStore:
    return SessionGraphStore()


def _context(
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RequestContext:
    return RequestContext(workspace_id=x_workspace_id or "default", user_id=x_user_id)


def _workspace_id(session: SessionRecord) -> str | None:
    value = session.metadata.get("workspace_id")
    return value if isinstance(value, str) else None


def _owner_user_id(session: SessionRecord) -> str | None:
    value = session.metadata.get("owner_user_id")
    return value if isinstance(value, str) else None


def _assert_session_visible(session: SessionRecord, context: RequestContext) -> None:
    workspace_id = _workspace_id(session)
    if workspace_id is not None and workspace_id != context.workspace_id:
        raise HTTPException(403, f"Session {session.id} is outside workspace {context.workspace_id}.")
    if session.policy.visibility == "private":
        owner_user_id = _owner_user_id(session)
        if owner_user_id is not None and owner_user_id != context.user_id:
            raise HTTPException(403, f"Session {session.id} is private.")


def _visible_sessions(sessions: list[SessionRecord], context: RequestContext) -> list[SessionRecord]:
    visible: list[SessionRecord] = []
    for session in sessions:
        try:
            _assert_session_visible(session, context)
        except HTTPException:
            continue
        visible.append(session)
    return visible


def _visible_ids(graph: SessionGraphSnapshot, context: RequestContext) -> set[str]:
    return {session.id for session in _visible_sessions(graph.sessions, context)}


def _get_visible_session(store: SessionGraphStore, session_id: str, context: RequestContext) -> SessionRecord:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _assert_session_visible(session, context)
    return session


def _get_session_from_graph(graph: SessionGraphSnapshot, session_id: str, context: RequestContext) -> SessionRecord:
    for session in graph.sessions:
        if session.id == session_id:
            _assert_session_visible(session, context)
            return session
    raise HTTPException(404, f"Session {session_id} not found")


def _get_edge_from_graph(graph: SessionGraphSnapshot, edge_id: str, context: RequestContext) -> SessionEdge:
    edge = next((candidate for candidate in graph.edges if candidate.id == edge_id), None)
    if edge is None:
        raise HTTPException(404, f"Edge {edge_id} not found")
    _get_session_from_graph(graph, edge.source_session_id, context)
    _get_session_from_graph(graph, edge.target_session_id, context)
    return edge


def _get_projection_from_graph(graph: SessionGraphSnapshot, projection_id: str, context: RequestContext) -> ContextProjection:
    projection = next((candidate for candidate in graph.projections if candidate.id == projection_id), None)
    if projection is None:
        raise HTTPException(404, f"Projection {projection.id} is outside workspace {context.workspace_id}.")
    _assert_projection_visible(graph, projection, context)
    return projection


def _assert_projection_visible(graph: SessionGraphSnapshot, projection: ContextProjection, context: RequestContext) -> None:
    visible = _visible_ids(graph, context)
    if projection.active_session_id in visible:
        return
    if any(source_id in visible for source_id in projection.source_session_ids):
        return
    raise HTTPException(403, f"Projection {projection.id} is outside workspace {context.workspace_id}.")


def _assert_projection_sessions_visible(graph: SessionGraphSnapshot, projection: ContextProjection, context: RequestContext) -> None:
    _get_session_from_graph(graph, projection.active_session_id, context)
    for source_session_id in projection.source_session_ids:
        _get_session_from_graph(graph, source_session_id, context)


def _stamp_session_scope(session: SessionRecord, context: RequestContext) -> SessionRecord:
    session.metadata.setdefault("workspace_id", context.workspace_id)
    if context.user_id:
        session.metadata.setdefault("owner_user_id", context.user_id)
    return session


def _append_event_to_graph(
    graph: SessionGraphSnapshot,
    session_id: str,
    event_type: str,
    data: dict[str, object] | None = None,
) -> SessionEvent:
    event = SessionEvent(
        type=event_type,
        session_id=session_id,
        actor=SessionEventActor.SYSTEM,
        data=data or {},
        created_at=utc_now(),
    )
    graph.events.append(event)
    return event


def _save_or_400(store: SessionGraphStore, graph: SessionGraphSnapshot) -> SessionGraphSnapshot:
    issues = validate_graph_update(graph)
    if issues:
        raise HTTPException(400, " ".join(issues))
    try:
        return store.save(graph)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _merge_dict(existing: dict[str, object], patch: dict[str, object], merge: bool) -> dict[str, object]:
    if not merge:
        return dict(patch)
    return {**existing, **patch}
