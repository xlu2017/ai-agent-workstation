"""Session graph — context projection CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.models.session_graph import (
    ContextProjection,
    ContextProjectionBudget,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
)
from api.routes.session_graph.helpers import (
    RequestContext,
    _append_event_to_graph,
    _assert_projection_sessions_visible,
    _assert_projection_visible,
    _context,
    _get_projection_from_graph,
    _get_session_from_graph,
    _get_visible_session,
    _save_or_400,
    _store,
    _visible_ids,
)

router = APIRouter()


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
