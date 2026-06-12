from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.models.session_graph import (
    AdapterMapping,
    ContextProjection,
    ContextProjectionBudget,
    EdgeType,
    MountSessionRequest,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
    SessionEdge,
    SessionEvent,
    SessionGraphSnapshot,
    SessionKind,
    SessionPolicy,
    SessionRecord,
    SessionStatus,
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
    """Header-backed workspace scope for the session graph API."""

    workspace_id: str = "default"
    user_id: str | None = None


class CreateEdgeRequest(BaseModel):
    type: EdgeType
    source_session_id: str
    target_session_id: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    status: SessionStatus | None = None
    parent_id: str | None = None
    facets: dict[str, dict[str, object]] | None = None
    policy: SessionPolicy | None = None
    state: dict[str, object] | None = None
    metadata: dict[str, object] | None = None
    merge_facets: bool = True
    merge_state: bool = True
    merge_metadata: bool = True
    reason: str = "Update session graph session."


class UpdateEdgeRequest(BaseModel):
    type: EdgeType | None = None
    source_session_id: str | None = None
    target_session_id: str | None = None
    metadata: dict[str, object] | None = None
    merge_metadata: bool = True
    reason: str = "Update session graph edge."


class UpdateProjectionRequest(BaseModel):
    active_session_id: str | None = None
    source_session_ids: list[str] | None = None
    projection_mode: ProjectionMode | None = None
    projection_source: ProjectionSource | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] | None = None
    include_selectors: list[ProjectionSelector] | None = None
    exclude_selectors: list[ProjectionSelector] | None = None
    budget: ContextProjectionBudget | None = None
    rationale: str | None = None
    reason: str = "Update context projection."


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
        raise HTTPException(404, f"Projection {projection_id} not found")
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
    try:
        session = _store().create_session(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"session": session.model_dump(mode="json")}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    session = _get_visible_session(_store(), session_id, context)
    return {"session": session.model_dump(mode="json")}


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    graph = store.load()
    index = next((idx for idx, session in enumerate(graph.sessions) if session.id == session_id), None)
    if index is None:
        raise HTTPException(404, f"Session {session_id} not found")

    session = graph.sessions[index]
    _assert_session_visible(session, context)
    before = session.model_dump(mode="json")
    fields = body.model_fields_set

    if "title" in fields and body.title is not None:
        session.title = body.title
    if "summary" in fields and body.summary is not None:
        session.summary = body.summary
    if "status" in fields and body.status is not None:
        session.status = body.status
    if "parent_id" in fields:
        if body.parent_id is None:
            session.parent_id = None
            session.root_id = session.id
        else:
            if body.parent_id == session.id:
                raise HTTPException(400, "Session cannot be its own parent.")
            parent = _get_session_from_graph(graph, body.parent_id, context)
            session.parent_id = parent.id
            session.root_id = parent.root_id or parent.id
    if body.facets is not None:
        session.facets = _merge_dict(session.facets, body.facets, body.merge_facets)  # type: ignore[arg-type]
    if body.policy is not None:
        session.policy = body.policy
    if body.state is not None:
        session.state = _merge_dict(session.state, body.state, body.merge_state)
    if body.metadata is not None:
        merged = _merge_dict(session.metadata, body.metadata, body.merge_metadata)
        merged.setdefault("workspace_id", context.workspace_id)
        if context.user_id:
            merged.setdefault("owner_user_id", context.user_id)
        session.metadata = merged

    session.updated_at = utc_now()
    graph.sessions[index] = session
    event = _append_event_to_graph(
        graph,
        session.id,
        "session.updated",
        {"before": before, "after": session.model_dump(mode="json"), "reason": body.reason, "source": "session_graph.crud"},
    )
    _save_or_400(store, graph)
    return {"session": session.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    cascade: bool = Query(False),
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    graph = store.load()
    session = _get_session_from_graph(graph, session_id, context)

    child_ids = {candidate.id for candidate in graph.sessions if candidate.parent_id == session.id}
    related_edges = [edge for edge in graph.edges if edge.source_session_id == session.id or edge.target_session_id == session.id]
    related_projections = [projection for projection in graph.projections if projection.active_session_id == session.id or session.id in projection.source_session_ids]
    if not cascade and (child_ids or related_edges or related_projections):
        raise HTTPException(
            409,
            "Session has child sessions, edges, or projections. Pass cascade=true to remove graph relationships.",
        )

    delete_ids = {session.id}
    if cascade:
        changed = True
        while changed:
            changed = False
            for candidate in graph.sessions:
                if candidate.parent_id in delete_ids and candidate.id not in delete_ids:
                    _assert_session_visible(candidate, context)
                    delete_ids.add(candidate.id)
                    changed = True

    removed_edges = [edge.id for edge in graph.edges if edge.source_session_id in delete_ids or edge.target_session_id in delete_ids]
    removed_projections = [
        projection.id
        for projection in graph.projections
        if projection.active_session_id in delete_ids or any(source_id in delete_ids for source_id in projection.source_session_ids)
    ]
    graph.sessions = [candidate for candidate in graph.sessions if candidate.id not in delete_ids]
    graph.edges = [edge for edge in graph.edges if edge.source_session_id not in delete_ids and edge.target_session_id not in delete_ids]
    graph.projections = [
        projection for projection in graph.projections
        if projection.active_session_id not in delete_ids and not any(source_id in delete_ids for source_id in projection.source_session_ids)
    ]
    event = _append_event_to_graph(
        graph,
        "session-graph",
        "session.updated",
        {
            "operation": "delete_session",
            "deleted_session_ids": sorted(delete_ids),
            "removed_edge_ids": removed_edges,
            "removed_projection_ids": removed_projections,
            "cascade": cascade,
        },
    )
    _save_or_400(store, graph)
    return {
        "deleted_session_ids": sorted(delete_ids),
        "removed_edge_ids": removed_edges,
        "removed_projection_ids": removed_projections,
        "event": event.model_dump(mode="json"),
    }


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
    visible_ids = _visible_ids(graph, context)
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
    event = _append_event_to_graph(
        graph,
        target.id,
        "session.linked",
        {"edge": edge.model_dump(mode="json")},
    )
    _save_or_400(store, graph)
    return {"edge": edge.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.get("/edges/{edge_id}")
def get_session_edge(
    edge_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    graph = _store().load()
    edge = _get_edge_from_graph(graph, edge_id, context)
    return {"edge": edge.model_dump(mode="json")}


@router.patch("/edges/{edge_id}")
def update_session_edge(
    edge_id: str,
    body: UpdateEdgeRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    graph = store.load()
    index = next((idx for idx, edge in enumerate(graph.edges) if edge.id == edge_id), None)
    if index is None:
        raise HTTPException(404, f"Edge {edge_id} not found")
    edge = graph.edges[index]
    _get_session_from_graph(graph, edge.source_session_id, context)
    _get_session_from_graph(graph, edge.target_session_id, context)
    before = edge.model_dump(mode="json")

    if body.type is not None:
        edge.type = body.type
    if body.source_session_id is not None:
        _get_session_from_graph(graph, body.source_session_id, context)
        edge.source_session_id = body.source_session_id
    if body.target_session_id is not None:
        _get_session_from_graph(graph, body.target_session_id, context)
        edge.target_session_id = body.target_session_id
    if edge.source_session_id == edge.target_session_id:
        raise HTTPException(400, "Edge source and target must be different sessions.")
    if body.metadata is not None:
        edge.metadata = _merge_dict(edge.metadata, body.metadata, body.merge_metadata)
    graph.edges[index] = edge
    event = _append_event_to_graph(
        graph,
        edge.target_session_id,
        "session.linked",
        {"operation": "update_edge", "before": before, "after": edge.model_dump(mode="json"), "reason": body.reason},
    )
    _save_or_400(store, graph)
    return {"edge": edge.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.delete("/edges/{edge_id}")
def delete_session_edge(
    edge_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    graph = store.load()
    edge = _get_edge_from_graph(graph, edge_id, context)
    graph.edges = [candidate for candidate in graph.edges if candidate.id != edge_id]
    event = _append_event_to_graph(
        graph,
        edge.target_session_id,
        "session.unlinked",
        {"operation": "delete_edge", "edge": edge.model_dump(mode="json")},
    )
    _save_or_400(store, graph)
    return {"deleted_edge_id": edge_id, "event": event.model_dump(mode="json")}


@router.get("/projections")
def list_context_projections(
    session_id: str | None = Query(None),
    context: RequestContext = Depends(_context),
) -> dict[str, list[dict[str, object]]]:
    graph = _store().load()
    visible_ids = _visible_ids(graph, context)
    projections = graph.projections
    if session_id is not None:
        projections = [projection for projection in projections if projection.active_session_id == session_id or session_id in projection.source_session_ids]
    projections = [
        projection for projection in projections
        if projection.active_session_id in visible_ids or any(source_id in visible_ids for source_id in projection.source_session_ids)
    ]
    return {"projections": [projection.model_dump(mode="json") for projection in projections]}


@router.post("/projections")
def create_context_projection(
    body: ContextProjection,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    graph = store.load()
    _assert_projection_sessions_visible(graph, body, context)
    if any(existing.id == body.id for existing in graph.projections):
        raise HTTPException(400, f"Projection {body.id} already exists.")
    graph.projections.append(body)
    event = _append_event_to_graph(
        graph,
        body.active_session_id,
        "session.adapter_projection_created",
        {"projection": body.model_dump(mode="json"), "source": "session_graph.crud"},
    )
    _save_or_400(store, graph)
    return {"projection": body.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.get("/projections/{projection_id}")
def get_context_projection_by_id(
    projection_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    graph = _store().load()
    projection = _get_projection_from_graph(graph, projection_id, context)
    return {"projection": projection.model_dump(mode="json")}


@router.patch("/projections/{projection_id}")
def update_context_projection(
    projection_id: str,
    body: UpdateProjectionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    graph = store.load()
    index = next((idx for idx, projection in enumerate(graph.projections) if projection.id == projection_id), None)
    if index is None:
        raise HTTPException(404, f"Projection {projection_id} not found")
    projection = graph.projections[index]
    _assert_projection_visible(graph, projection, context)
    before = projection.model_dump(mode="json")

    if body.active_session_id is not None:
        _get_session_from_graph(graph, body.active_session_id, context)
        projection.active_session_id = body.active_session_id
    if body.source_session_ids is not None:
        for source_id in body.source_session_ids:
            _get_session_from_graph(graph, source_id, context)
        projection.source_session_ids = body.source_session_ids
    if body.projection_mode is not None:
        projection.projection_mode = body.projection_mode
    if body.projection_source is not None:
        projection.projection_source = body.projection_source
    if body.relevance_score is not None:
        projection.relevance_score = body.relevance_score
    if body.evidence is not None:
        projection.evidence = body.evidence
    if body.include_selectors is not None:
        projection.include_selectors = body.include_selectors
    if body.exclude_selectors is not None:
        projection.exclude_selectors = body.exclude_selectors
    if body.budget is not None:
        projection.budget = body.budget
    if body.rationale is not None:
        projection.rationale = body.rationale

    graph.projections[index] = projection
    event = _append_event_to_graph(
        graph,
        projection.active_session_id,
        "session.adapter_projection_created",
        {"operation": "update_projection", "before": before, "after": projection.model_dump(mode="json"), "reason": body.reason},
    )
    _save_or_400(store, graph)
    return {"projection": projection.model_dump(mode="json"), "event": event.model_dump(mode="json")}


@router.delete("/projections/{projection_id}")
def delete_context_projection(
    projection_id: str,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    graph = store.load()
    projection = _get_projection_from_graph(graph, projection_id, context)
    graph.projections = [candidate for candidate in graph.projections if candidate.id != projection_id]
    event = _append_event_to_graph(
        graph,
        projection.active_session_id,
        "session.updated",
        {"operation": "delete_projection", "projection": projection.model_dump(mode="json")},
    )
    _save_or_400(store, graph)
    return {"deleted_projection_id": projection_id, "event": event.model_dump(mode="json")}


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
    _save_or_400(store, graph)
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
    visible_ids = _visible_ids(graph, context)
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
