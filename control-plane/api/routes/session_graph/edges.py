"""Session graph — edge CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.models.session_graph import EdgeType, SessionEdge
from api.routes.session_graph.helpers import (
    RequestContext,
    _append_event_to_graph,
    _context,
    _get_edge_from_graph,
    _get_session_from_graph,
    _get_visible_session,
    _merge_dict,
    _save_or_400,
    _store,
    _visible_ids,
)

router = APIRouter()


class CreateEdgeRequest(BaseModel):
    type: EdgeType
    source_session_id: str
    target_session_id: str
    metadata: dict[str, object] = Field(default_factory=dict)


class UpdateEdgeRequest(BaseModel):
    type: EdgeType | None = None
    source_session_id: str | None = None
    target_session_id: str | None = None
    metadata: dict[str, object] | None = None
    merge_metadata: bool = True
    reason: str = "Update session graph edge."


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
