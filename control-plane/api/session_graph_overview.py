from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from api.models.session_graph import SessionGraphSnapshot, SessionRecord
from api.services.session_graph_service import SessionGraphStore


router = APIRouter(prefix="/api/session-graph", tags=["session-graph"])


class RequestContext(BaseModel):
    workspace_id: str = "default"
    user_id: str | None = None


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


def _session_visible(session: SessionRecord, context: RequestContext) -> bool:
    workspace_id = _workspace_id(session)
    if workspace_id is not None and workspace_id != context.workspace_id:
        return False
    if session.policy.visibility == "private":
        owner_user_id = _owner_user_id(session)
        if owner_user_id is not None and owner_user_id != context.user_id:
            return False
    return True


def _visible_ids(graph: SessionGraphSnapshot, context: RequestContext) -> set[str]:
    return {session.id for session in graph.sessions if _session_visible(session, context)}


def _count(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


@router.get("/overview")
def get_session_graph_overview(context: RequestContext = Depends(_context)) -> dict[str, Any]:
    graph = SessionGraphStore().load()
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
