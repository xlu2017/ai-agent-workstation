"""Session graph chat routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import (
    EdgeType,
    SessionEdge,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
    SessionKind,
    SessionRecord,
    SessionStatus,
    utc_now,
)
from api.routes.session_graph.helpers import RequestContext, _assert_session_visible, _context, _save_or_400, _store

router = APIRouter()


class GraphSessionChatRequest(BaseModel):
    content: str = Field(min_length=1)
    role: str = "user"
    mode: str | None = None


def _short_title(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= 76 else f"{normalized[:76]}…"


@router.post("/sessions/{session_id}/chat")
def append_graph_session_chat_turn(
    session_id: str,
    body: GraphSessionChatRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    """Append a user chat turn and create a graph work session for it."""
    if body.role != "user":
        raise HTTPException(400, "Only user chat turns are accepted by this endpoint.")

    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Chat content cannot be empty.")

    store = _store()
    graph = store.load()
    index = next((idx for idx, session in enumerate(graph.sessions) if session.id == session_id), None)
    if index is None:
        raise HTTPException(404, f"Session {session_id} not found")

    session = graph.sessions[index]
    _assert_session_visible(session, context)

    now = utc_now()
    repo_needed = not bool(session.metadata.get("repo_session_id"))
    turns = session.state.get("chat_turns", [])
    if not isinstance(turns, list):
        turns = []
    turn = {"role": "user", "content": content, "created_at": now}
    turns.append(turn)

    session.state = {**session.state, "chat_turns": turns, "last_user_message": content}
    session.metadata = {**session.metadata, "last_graph_chat_at": now, "graph_chat_status": "work_created"}
    session.updated_at = now
    graph.sessions[index] = session

    user_event = SessionEvent(
        type=SessionEventType.USER_INTERJECTED,
        session_id=session.id,
        root_session_id=session.root_id or session.id,
        actor=SessionEventActor.USER,
        data={"content": content, "mode": body.mode, "source": "session_graph.chat"},
        created_at=now,
    )

    work_session = SessionRecord(
        kind=SessionKind.WORK,
        title=_short_title(content),
        summary=content,
        status=SessionStatus.BLOCKED if repo_needed else SessionStatus.ACTIVE,
        parent_id=session.id,
        root_id=session.root_id or session.id,
        facets={"work": {"prompt": content, "source_session_id": session.id, "mode": body.mode or "finite", "requires_repo": repo_needed}},
        state={"chat_turns": [turn], "status_reason": "needs_repo" if repo_needed else "ready"},
        metadata={
            "workspace_id": session.metadata.get("workspace_id", context.workspace_id),
            "owner_user_id": session.metadata.get("owner_user_id") or context.user_id,
            "created_from": "session_graph_chat",
            "repo_session_id": session.metadata.get("repo_session_id"),
        },
        created_at=now,
        updated_at=now,
        created_from_event_id=user_event.id,
    )
    graph.sessions.append(work_session)

    work_edge = SessionEdge(
        type=EdgeType.COMPONENT_OF,
        source_session_id=work_session.id,
        target_session_id=session.id,
        metadata={"reason": "Graph chat created a work session.", "source": "session_graph.chat"},
        created_at=now,
        created_from_event_id=user_event.id,
    )
    graph.edges.append(work_edge)

    work_event = SessionEvent(
        type=SessionEventType.WORK_STARTED,
        session_id=work_session.id,
        root_session_id=work_session.root_id,
        actor=SessionEventActor.SYSTEM,
        data={"parent_session_id": session.id, "prompt": content, "requires_repo": repo_needed, "source": "session_graph.chat"},
        created_at=now,
    )
    graph.events.extend([user_event, work_event])

    _save_or_400(store, graph)
    return {
        "session": session.model_dump(mode="json"),
        "turn": turn,
        "work_session": work_session.model_dump(mode="json"),
        "work_edge": work_edge.model_dump(mode="json"),
        "events": [user_event.model_dump(mode="json"), work_event.model_dump(mode="json")],
        "chat_status": "needs_repo" if repo_needed else "ready",
    }
