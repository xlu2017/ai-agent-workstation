"""Session graph — graph-native chat routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import SessionEvent, SessionEventActor, SessionEventType, utc_now
from api.routes.session_graph.helpers import RequestContext, _assert_session_visible, _context, _save_or_400, _store

router = APIRouter()


class GraphSessionChatRequest(BaseModel):
    content: str = Field(min_length=1)
    role: str = "user"
    execution_mode: str | None = None


@router.post("/sessions/{session_id}/chat")
def append_graph_session_chat_turn(
    session_id: str,
    body: GraphSessionChatRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    """Append a chat turn to a graph session without using deprecated runtime sessions.

    This endpoint is the stable graph-native chat contract. It records the user turn
    and emits graph events now; a later execution bridge can subscribe to the same
    event stream and create work/action sessions from the message.
    """
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

    turns = session.state.get("chat_turns", [])
    if not isinstance(turns, list):
        turns = []
    now = utc_now()
    turn = {"role": "user", "content": content, "created_at": now}
    turns.append(turn)

    session.state = {**session.state, "chat_turns": turns, "last_user_message": content}
    session.metadata = {
        **session.metadata,
        "last_graph_chat_at": now,
        "graph_chat_execution_bridge": "not_wired",
    }
    session.updated_at = now
    graph.sessions[index] = session

    user_event = SessionEvent(
        type=SessionEventType.USER_INTERJECTED,
        session_id=session.id,
        root_session_id=session.root_id or session.id,
        actor=SessionEventActor.USER,
        data={"content": content, "execution_mode": body.execution_mode, "source": "session_graph.chat"},
        created_at=now,
    )
    bridge_event = SessionEvent(
        type=SessionEventType.ACTION_PROPOSED,
        session_id=session.id,
        root_session_id=session.root_id or session.id,
        actor=SessionEventActor.SYSTEM,
        data={
            "action_name": "execution_bridge.continue_session",
            "status": "not_wired",
            "reason": "Graph-native chat recorded; execution bridge has not been connected yet.",
            "requires_repo_before_execution": not bool(session.metadata.get("repo_session_id")),
            "source": "session_graph.chat",
        },
        created_at=now,
    )
    graph.events.extend([user_event, bridge_event])

    _save_or_400(store, graph)
    return {
        "session": session.model_dump(mode="json"),
        "turn": turn,
        "events": [user_event.model_dump(mode="json"), bridge_event.model_dump(mode="json")],
        "execution_bridge_status": "not_wired",
    }
