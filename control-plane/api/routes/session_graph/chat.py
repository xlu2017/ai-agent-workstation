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
from api.services.session_graph_prompt_recommendation import recommend_graph_prompt_route

router = APIRouter()


class GraphSessionChatRequest(BaseModel):
    content: str = Field(min_length=1)
    role: str = "user"
    mode: str | None = None


def _short_title(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= 76 else f"{normalized[:76]}…"


def _chat_turns(session: SessionRecord) -> list[object]:
    turns = session.state.get("chat_turns", [])
    return turns if isinstance(turns, list) else []


def _base_metadata(session: SessionRecord, context: RequestContext) -> dict[str, object]:
    return {
        "workspace_id": session.metadata.get("workspace_id", context.workspace_id),
        "owner_user_id": session.metadata.get("owner_user_id") or context.user_id,
        "repo_session_id": session.metadata.get("repo_session_id"),
    }


def _make_work_session(session: SessionRecord, content: str, turn: dict[str, object], now: str, context: RequestContext, mode: str | None) -> SessionRecord:
    repo_needed = not bool(session.metadata.get("repo_session_id"))
    return SessionRecord(
        kind=SessionKind.WORK,
        title=_short_title(content),
        summary=content,
        status=SessionStatus.BLOCKED if repo_needed else SessionStatus.ACTIVE,
        parent_id=session.id,
        root_id=session.root_id or session.id,
        facets={"work": {"prompt": content, "source_session_id": session.id, "mode": mode or "finite", "requires_repo": repo_needed}},
        state={"chat_turns": [turn], "status_reason": "needs_repo" if repo_needed else "ready"},
        metadata={**_base_metadata(session, context), "created_from": "session_graph_chat"},
        created_at=now,
        updated_at=now,
    )


def _make_goal_session(session: SessionRecord, content: str, turn: dict[str, object], now: str, context: RequestContext, route: str) -> SessionRecord:
    child = route == "create_child_goal"
    goal = SessionRecord(
        kind=SessionKind.GOAL,
        title=_short_title(content),
        summary=content,
        status=SessionStatus.ACTIVE,
        parent_id=session.id if child else None,
        root_id=session.root_id or session.id if child else None,
        facets={"goal": {"initial_prompt": content, "created_from_followup": True, "route": route}},
        state={"initial_prompt": content, "chat_turns": [turn]},
        metadata={**_base_metadata(session, context), "created_from": "session_graph_chat", "source_session_id": session.id},
        created_at=now,
        updated_at=now,
    )
    if not child:
        goal.root_id = goal.id
    return goal


@router.post("/sessions/{session_id}/chat")
def append_graph_session_chat_turn(
    session_id: str,
    body: GraphSessionChatRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    """Append a user chat turn and route it through the graph session model."""
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
    classification = recommend_graph_prompt_route(session, content)
    turn = {"role": "user", "content": content, "created_at": now}
    turns = _chat_turns(session)
    turns.append(turn)

    session.state = {**session.state, "chat_turns": turns, "last_user_message": content}
    session.metadata = {
        **session.metadata,
        "last_graph_chat_at": now,
        "graph_chat_status": classification.route,
        "graph_chat_classification_reason": classification.reason,
        "graph_chat_recommendation_source": classification.source,
    }
    session.updated_at = now
    graph.sessions[index] = session

    user_event = SessionEvent(
        type=SessionEventType.USER_INTERJECTED,
        session_id=session.id,
        root_session_id=session.root_id or session.id,
        actor=SessionEventActor.USER,
        data={"content": content, "mode": body.mode, "route": classification.route, "source": "session_graph.chat"},
        created_at=now,
    )
    graph.events.append(user_event)

    created_session: SessionRecord | None = None
    created_edge: SessionEdge | None = None
    extra_event: SessionEvent | None = None
    chat_status = classification.route

    if classification.route == "continue_active":
        created_session = _make_work_session(session, content, turn, now, context, body.mode)
        created_session.created_from_event_id = user_event.id
        graph.sessions.append(created_session)
        created_edge = SessionEdge(
            type=EdgeType.COMPONENT_OF,
            source_session_id=created_session.id,
            target_session_id=session.id,
            metadata={"reason": "Graph chat created a work session.", "source": classification.source},
            created_at=now,
            created_from_event_id=user_event.id,
        )
        graph.edges.append(created_edge)
        extra_event = SessionEvent(
            type=SessionEventType.WORK_STARTED,
            session_id=created_session.id,
            root_session_id=created_session.root_id,
            actor=SessionEventActor.SYSTEM,
            data={"parent_session_id": session.id, "prompt": content, "requires_repo": not bool(session.metadata.get("repo_session_id")), "source": classification.source},
            created_at=now,
        )
        chat_status = "needs_repo" if created_session.status == SessionStatus.BLOCKED else "ready"

    elif classification.route in {"create_child_goal", "create_sibling_goal"}:
        created_session = _make_goal_session(session, content, turn, now, context, classification.route)
        created_session.created_from_event_id = user_event.id
        graph.sessions.append(created_session)
        created_edge = SessionEdge(
            type=EdgeType.COMPONENT_OF if classification.route == "create_child_goal" else EdgeType.SIBLING_OF,
            source_session_id=created_session.id,
            target_session_id=session.id,
            metadata={"reason": classification.reason, "source": classification.source},
            created_at=now,
            created_from_event_id=user_event.id,
        )
        graph.edges.append(created_edge)
        extra_event = SessionEvent(
            type=SessionEventType.GOAL_CREATED,
            session_id=created_session.id,
            root_session_id=created_session.root_id or created_session.id,
            actor=SessionEventActor.SYSTEM,
            data={"source_session_id": session.id, "route": classification.route, "prompt": content, "source": classification.source},
            created_at=now,
        )

    else:
        extra_event = SessionEvent(
            type=SessionEventType.OBSERVATION_RECORDED,
            session_id=session.id,
            root_session_id=session.root_id or session.id,
            actor=SessionEventActor.SYSTEM,
            data={"route": classification.route, "reason": classification.reason, "source": classification.source},
            created_at=now,
        )

    if extra_event is not None:
        graph.events.append(extra_event)

    _save_or_400(store, graph)
    response: dict[str, object] = {
        "session": session.model_dump(mode="json"),
        "turn": turn,
        "routing_decision": {"route": classification.route, "reason": classification.reason, "source": classification.source},
        "events": [event.model_dump(mode="json") for event in [user_event, extra_event] if event is not None],
        "chat_status": chat_status,
    }
    if created_session is not None:
        key = "work_session" if created_session.kind == SessionKind.WORK else "goal_session"
        response[key] = created_session.model_dump(mode="json")
    if created_edge is not None:
        response["created_edge"] = created_edge.model_dump(mode="json")
    return response
