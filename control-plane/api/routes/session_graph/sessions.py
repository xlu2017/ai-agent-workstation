"""Session graph — session CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.models.session_graph import (
    SessionPolicy,
    SessionRecord,
    SessionStatus,
    utc_now,
)
from api.routes.session_graph.helpers import (
    RequestContext,
    _append_event_to_graph,
    _assert_session_visible,
    _context,
    _get_session_from_graph,
    _get_visible_session,
    _merge_dict,
    _save_or_400,
    _stamp_session_scope,
    _store,
    _visible_sessions,
)
from api.services.session_graph_repo_execution import (
    execution_context_was_attached,
    reactivate_blocked_work_sessions_after_repo_attach,
)

router = APIRouter()


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
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    graph = store.load()
    index = next((idx for idx, session in enumerate(graph.sessions) if session.id == session_id), None)
    if index is None:
        raise HTTPException(404, f"Session {session_id} not found")

    session = graph.sessions[index]
    _assert_session_visible(session, context)
    before = session.model_dump(mode="json")
    before_metadata = dict(session.metadata)
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

    reactivated_work_sessions: list[dict[str, object]] = []
    if execution_context_was_attached(before_metadata, session.metadata):
        reactivated_work_sessions = await reactivate_blocked_work_sessions_after_repo_attach(
            graph=graph,
            parent_session=session,
            source_event_id=event.id,
        )

    _save_or_400(store, graph)
    return {
        "session": session.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "reactivated_work_sessions": reactivated_work_sessions,
        "reactivated_work_session_count": len(reactivated_work_sessions),
    }


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
