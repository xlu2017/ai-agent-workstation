from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.models.session_graph import (
    AdapterMapping,
    ContextProjection,
    EdgeType,
    MountSessionRequest,
    MountSessionResult,
    SessionEdge,
    SessionEvent,
    SessionGraphSnapshot,
    SessionKind,
    SessionRecord,
    SessionUpdateProposal,
    utc_now,
)
from api.services.platform_settings import (
    ObservabilitySettings,
    get_observability_settings,
    update_observability_settings,
)
from api.services.session_adapter_engine import adapt_session, mount_session, preview_mount_session
from api.services.session_graph_service import SessionGraphStore, validate_graph_update


router = APIRouter(prefix="/api/session-graph", tags=["session-graph"])


class RequestContext(BaseModel):
    """Lightweight scaffold for workspace/user scoping.

    This is not a replacement for real authentication. It gives the session graph
    API a single enforcement point so future auth can replace the header-backed
    context without changing every route.
    """

    workspace_id: str = "default"
    user_id: str | None = None


class CreateEdgeRequest(BaseModel):
    type: EdgeType
    source_session_id: str
    target_session_id: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UnmountSessionRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    reason: str = "Unmount session from target context."
    remove_adapter_edges: bool = False


class UpdateAdapterMappingsRequest(BaseModel):
    mode: Literal["replace", "append"] = "replace"
    mappings: list[AdapterMapping] = Field(default_factory=list)
    reason: str = "Update adapter mappings."


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


def _get_visible_session(store: SessionGraphStore, session_id: str, context: RequestContext) -> SessionRecord:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _assert_session_visible(session, context)
    return session


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
        data=data or {},
        created_at=utc_now(),
    )
    graph.events.append(event)
    return event


@router.get("/sessions")
def list_sessions(context: RequestContext = Depends(_context)) -> dict[str, list[dict[str, object]]]:
    sessions = _visible_sessions(_store().list_sessions(), context)
    return {"sessions": [session.model_dump(mode="json") for session in sessions]}


@router.post("/sessions")
def create_session(
    body: SessionRecord,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    body = _stamp_session_scope(body, context)
    return {"session": _store().create_session(body).model_dump(mode="json")}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    session = _get_visible_session(_store(), session_id, context)
    return {"session": session.model_dump(mode="json")}


@router.get("/edges")
def list_session_edges(
    session_id: str | None = Query(None),
    source_session_id: str | None = Query(None),
    target_session_id: str | None = Query(None),
    edge_type: EdgeType | None = Query(None),
    context: RequestContext = Depends(_context),
) -> dict[str, list[dict[str, object]]]:
    store = _store()
    graph = store.load()
    visible_ids = {session.id for session in _visible_sessions(graph.sessions, context)}
    edges = graph.edges
    if session_id is not None:
        edges = [edge for edge in edges if edge.source_session_id == session_id or edge.target_session_id == session_id]
    if source_session_id is not None:
        edges = [edge for edge in edges if edge.source_session_id == source_session_id]
    if target_session_id is not None:
        edges = [edge for edge in edges if edge.target_session_id == target_session_id]
    if edge_type is not None:
        edges = [edge for edge in edges if edge.type == edge_type]
    edges = [edge for edge in edges if edge.source_session_id in visible_ids and edge.target_session_id in visible_ids]
    return {"edges": [edge.model_dump(mode="json") for edge in edges]}


@router.post("/edges")
def create_session_edge(
    body: CreateEdgeRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    source = _get_visible_session(store, body.source_session_id, context)
    target = _get_visible_session(store, body.target_session_id, context)
    graph = store.load()
    edge = SessionEdge(
        type=body.type,
        source_session_id=source.id,
        target_session_id=target.id,
        metadata={**body.metadata, "created_by_route": "session_graph.create_edge"},
    )
    graph.edges.append(edge)
    _append_event_to_graph(
        graph,
        target.id,
        "session.linked",
        {"edge": edge.model_dump(mode="json")},
    )
    issues = validate_graph_update(graph)
    if issues:
        raise HTTPException(400, " ".join(issues))
    store.save(graph)
    return {"edge": edge.model_dump(mode="json")}


@router.post("/mount/preview")
def preview_mount_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        result = preview_mount_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.post("/mount")
def mount_session_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        result = mount_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.post("/unmount")
def unmount_session_endpoint(
    body: UnmountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
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
        raise HTTPException(404, "No mounted edge found for source and target sessions.")

    graph.edges = retained_edges
    event = _append_event_to_graph(
        graph,
        body.target_session_id,
        "session.unmounted",
        {
            "source_session_id": body.source_session_id,
            "target_session_id": body.target_session_id,
            "removed_edge_ids": removed_edge_ids,
            "reason": body.reason,
            "remove_adapter_edges": body.remove_adapter_edges,
        },
    )
    issues = validate_graph_update(graph)
    if issues:
        raise HTTPException(400, " ".join(issues))
    store.save(graph)
    return {"removed_edge_ids": removed_edge_ids, "event": event.model_dump(mode="json")}


@router.post("/adapt")
def adapt_session_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        session = adapt_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"session": session.model_dump(mode="json")}


@router.put("/adapters/{adapter_session_id}/mappings")
def update_adapter_mappings(
    adapter_session_id: str,
    body: UpdateAdapterMappingsRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    adapter = _get_visible_session(store, adapter_session_id, context)
    if adapter.kind != SessionKind.ADAPTER:
        raise HTTPException(400, f"Session {adapter_session_id} is not an adapter session.")

    graph = store.load()
    updated_session: SessionRecord | None = None
    for session in graph.sessions:
        if session.id != adapter_session_id:
            continue
        adapter_facet = dict(session.facets.get("adapter", {}))
        existing_mappings = adapter_facet.get("mappings", [])
        new_mappings = [mapping.model_dump(mode="json") for mapping in body.mappings]
        adapter_facet["mappings"] = [*existing_mappings, *new_mappings] if body.mode == "append" else new_mappings
        adapter_facet["mapping_status"] = "mapping" if adapter_facet["mappings"] else "proposed"
        session.facets["adapter"] = adapter_facet
        session.updated_at = utc_now()
        updated_session = session
        break

    if updated_session is None:
        raise HTTPException(404, f"Adapter session {adapter_session_id} not found")

    event = _append_event_to_graph(
        graph,
        adapter_session_id,
        "session.adapter_mapping_added",
        {
            "mode": body.mode,
            "mapping_count": len(body.mappings),
            "reason": body.reason,
        },
    )
    store.save(graph)
    return {"session": updated_session.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.get("/events")
def list_session_events(
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    context: RequestContext = Depends(_context),
) -> dict[str, list[dict[str, object]]]:
    graph = _store().load()
    visible_ids = {session.id for session in _visible_sessions(graph.sessions, context)}
    events = graph.events
    if session_id is not None:
        events = [event for event in events if event.session_id == session_id]
    if event_type is not None:
        events = [event for event in events if event.type == event_type]
    events = [event for event in events if event.session_id in visible_ids or event.session_id == "session-graph"]
    return {"events": [event.model_dump(mode="json") for event in events]}


@router.get("/context-projection/{session_id}")
def get_context_projection(
    session_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    _get_visible_session(_store(), session_id, context)
    projection = _store().get_projection_for(session_id)
    if projection is None:
        raise HTTPException(404, f"Context projection for {session_id} not found")
    return {"projection": projection.model_dump(mode="json")}


@router.post("/session-update/apply")
def apply_session_update(
    body: SessionUpdateProposal,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    if body.active_session_id is not None:
        _get_visible_session(store, body.active_session_id, context)
    try:
        graph = store.apply_update_proposal(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"graph": graph.model_dump(mode="json")}


@router.get("/snapshot")
def get_snapshot(context: RequestContext = Depends(_context)) -> dict[str, dict[str, object]]:
    graph = _store().load()
    visible_sessions = _visible_sessions(graph.sessions, context)
    visible_ids = {session.id for session in visible_sessions}
    scoped = SessionGraphSnapshot(
        sessions=visible_sessions,
        edges=[
            edge for edge in graph.edges
            if edge.source_session_id in visible_ids and edge.target_session_id in visible_ids
        ],
        events=[event for event in graph.events if event.session_id in visible_ids or event.session_id == "session-graph"],
        projections=[
            projection for projection in graph.projections
            if projection.active_session_id in visible_ids or any(source_id in visible_ids for source_id in projection.source_session_ids)
        ],
    )
    return {"graph": scoped.model_dump(mode="json")}


@router.get("/settings/observability")
def get_observability_settings_endpoint() -> dict[str, dict[str, object]]:
    return {"settings": get_observability_settings().model_dump(mode="json")}


@router.put("/settings/observability")
def update_observability_settings_endpoint(
    body: ObservabilitySettings,
) -> dict[str, dict[str, object]]:
    updated = update_observability_settings(body)
    return {"settings": updated.model_dump(mode="json")}
