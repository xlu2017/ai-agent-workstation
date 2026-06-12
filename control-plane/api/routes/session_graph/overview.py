from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends

from api.routes.session_graph.helpers import RequestContext, _context, _store, _visible_ids

router = APIRouter()


def _count(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


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
    latest = max(events, key=lambda item: item.created_at, default=None)

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
            "latest": latest.model_dump(mode="json") if latest else None,
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
