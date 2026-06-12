"""Session graph snapshot, overview, and session-update routes."""

from __future__ import annotations

from collections import Counter
from typing import Any

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
    _visible_ids,
    _visible_sessions,
)

router = APIRouter()


def _count(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


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


@router.get("/overview")
def get_session_graph_overview(context: RequestContext = Depends(_context)) -> dict[str, Any]:
    graph = _store().load()
    visible_ids = _visible_ids(graph, context)
    sessions = [session for session in graph.sessions if session.id in visible_ids]
    edges = [edge for edge in graph.edges if edge.source_session_id in visible_ids and edge.target_session_id in visible_ids]
    events = [event for event in graph.events if event.session_id in visible_ids or event.session_id == "session-graph"]
    projections = [
        projection
        for projection in graph.projections
        if projection.active_session_id in visible_ids
        or any(source_id in visible_ids for source_id in projection.source_session_ids)
    ]
    latest_event = max(events, key=lambda event: event.created_at, default=None)

    return {
        "sessions": {
            "total": len(sessions),
            "by_kind": _count([session.kind.value for session in sessions]),
            "by_status": _count([session.status.value for session in sessions]),
            "roots": len({session.root_id or session.id for session in sessions}),
        },
        "edges": {
            "total": len(edges),
            "by_type": _count([edge.type.value for edge in edges]),
        },
        "events": {
            "total": len(events),
            "latest": latest_event.model_dump(mode="json") if latest_event else None,
        },
        "projections": {
            "total": len(projections),
            "total_budget": {
                "max_tokens": sum(projection.budget.max_tokens for projection in projections),
                "max_files": sum(projection.budget.max_files for projection in projections),
                "max_events": sum(projection.budget.max_events for projection in projections),
            },
        },
    }


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
