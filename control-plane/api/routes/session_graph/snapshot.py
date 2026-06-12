"""Session graph — snapshot and session-update-apply routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.models.session_graph import (
    SessionGraphSnapshot,
    SessionUpdateProposal,
)
from api.routes.session_graph.helpers import (
    RequestContext,
    _context,
    _get_visible_session,
    _store,
    _visible_sessions,
)

router = APIRouter()


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
