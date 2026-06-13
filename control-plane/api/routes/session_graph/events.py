"""Session graph — event listing route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.routes.session_graph.helpers import (
    RequestContext,
    _context,
    _store,
    _visible_ids,
)

router = APIRouter()


@router.get("/events")
def list_session_events(
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    include_root_children: bool = Query(True),
    context: RequestContext = Depends(_context),
) -> dict[str, list[dict[str, object]]]:
    graph = _store().load()
    visible_ids = _visible_ids(graph, context)
    events = graph.events
    if session_id is not None:
        events = [
            event
            for event in events
            if event.session_id == session_id or (include_root_children and event.root_session_id == session_id)
        ]
    if event_type is not None:
        events = [event for event in events if event.type == event_type]
    events = [event for event in events if event.session_id in visible_ids or event.session_id == "session-graph"]
    return {"events": [event.model_dump(mode="json") for event in events]}
