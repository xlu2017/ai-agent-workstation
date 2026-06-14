"""Session graph chat routes."""

from __future__ import annotations

import os
from pathlib import Path

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
from api.services.session_graph_execution_bridge import (
    build_graph_work_execution_readiness_request,
    execution_readiness_response,
    record_execution_readiness_on_work_session,
    start_graph_workflow,
)
from api.services.session_graph_prompt_recommendation import PromptRoutingUnavailable, recommend_graph_prompt_route
from execution.activation import ExecutionActivationService

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
        "repo_id": session.metadata.get("repo_id"),
        "worktree_id": session.metadata.get("worktree_id"),
        "repo_path": session.metadata.get("repo_path"),
        "allowed_actions": session.metadata.get("allowed_actions"),
    }


def _work_execution_state(repo_needed: bool) -> str:
    return "blocked_needs_repo" if repo_needed else "ready_for_execution"


def _make_work_session(
    session: SessionRecord,
    content: str,
    turn: dict[str, object],
    now: str,
    context: RequestContext,
    mode: str | None,
    narration: str = "",
) -> SessionRecord:
    repo_needed = not bool(session.metadata.get("repo_session_id"))
    execution_state = _work_execution_state(repo_needed)
    base_metadata = _base_metadata(session, context)
    allowed_actions = base_metadata.get("allowed_actions")
    work_facet = {
        "prompt": content,
        "source_session_id": session.id,
        "mode": mode or "finite",
        "requires_repo": repo_needed,
        "execution_state": execution_state,
        "auto_started": False,
        "requires_execution_start": not repo_needed,
    }
    if isinstance(allowed_actions, list):
        work_facet["allowed_actions"] = allowed_actions
    state = {
        "chat_turns": [turn],
        "status_reason": "needs_repo" if repo_needed else "ready_for_execution",
        "execution_state": execution_state,
        "auto_started": False,
    }
    if narration:
        work_facet["narration"] = narration
        state["narration"] = narration
    return SessionRecord(
        kind=SessionKind.WORK,
        title=_short_title(content),
        summary=content,
        status=SessionStatus.BLOCKED if repo_needed else SessionStatus.ACTIVE,
        parent_id=session.id,
        root_id=session.root_id or session.id,
        facets={"work": work_facet},
        state=state,
        metadata={**base_metadata, "created_from": "session_graph_chat"},
        created_at=now,
        updated_at=now,
    )


def _make_chat_session(
    session: SessionRecord,
    content: str,
    user_turn: dict[str, object],
    assistant_turn: dict[str, object],
    now: str,
    context: RequestContext,
    route_source: str,
) -> SessionRecord:
    return SessionRecord(
        kind=SessionKind.CHAT,
        title=_short_title(content),
        summary=str(assistant_turn.get("content") or content),
        status=SessionStatus.COMPLETED,
        parent_id=session.id,
        root_id=session.root_id or session.id,
        facets={
            "chat": {
                "prompt": content,
                "response": assistant_turn.get("content") or "",
                "source_session_id": session.id,
                "route_source": route_source,
                "non_executable": True,
            }
        },
        state={
            "chat_turns": [user_turn, assistant_turn],
            "execution_state": "answered_inline",
            "auto_started": False,
        },
        metadata={**_base_metadata(session, context), "created_from": "session_graph_chat", "non_executable": True},
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


def _repo_facet(session: SessionRecord) -> dict[str, object]:
    facet = session.facets.get("repo", {})
    return facet if isinstance(facet, dict) else {}


def _worktree_id_from_local_path(path_text: str) -> str:
    path = Path(path_text).expanduser()
    worktree_base = Path(os.environ.get("WORKTREE_BASE", os.environ.get("REPOS_DIR", "/opt/workstation/repos"))).expanduser()
    try:
        return str(path.resolve().relative_to(worktree_base.resolve()))
    except (OSError, ValueError):
        return ""


def _apply_repo_execution_metadata(work_session: SessionRecord, parent_session: SessionRecord, graph_sessions: list[SessionRecord]) -> SessionRecord:
    repo_session_id = str(parent_session.metadata.get("repo_session_id") or work_session.metadata.get("repo_session_id") or "")
    if not repo_session_id:
        return work_session

    repo_session = next((candidate for candidate in graph_sessions if candidate.id == repo_session_id), None)
    if repo_session is None:
        return work_session

    repo = _repo_facet(repo_session)
    metadata_patch: dict[str, object] = {"repo_session_id": repo_session.id}
    source = str(repo.get("source") or "")
    if source == "local":
        repo_path = str(repo.get("path") or "")
        worktree_id = _worktree_id_from_local_path(repo_path) if repo_path else ""
        metadata_patch.update({
            "repo_id": repo_session.id,
            "repo_path": repo_path,
            "worktree_id": worktree_id,
            "repo_source": "local",
        })
    elif source == "github":
        metadata_patch.update({
            "repo_id": str(repo.get("full_name") or repo_session.id),
            "repo_source": "github",
            "clone_url": repo.get("clone_url") or "",
        })

    work_session.metadata = {**work_session.metadata, **metadata_patch}
    return work_session


@router.post("/sessions/{session_id}/chat")
async def append_graph_session_chat_turn(
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
    try:
        classification = recommend_graph_prompt_route(session, content)
    except PromptRoutingUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "prompt_routing_unavailable",
                "message": "Prompt routing is unavailable because agent-core or its configured LLM is unavailable or returned an invalid route.",
                "reason": str(exc),
            },
        ) from exc
    narration = classification.narration
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
    if narration:
        session.metadata["graph_chat_narration"] = narration
    session.updated_at = now
    graph.sessions[index] = session

    user_event = SessionEvent(
        type=SessionEventType.USER_INTERJECTED,
        session_id=session.id,
        root_session_id=session.root_id or session.id,
        actor=SessionEventActor.USER,
        data={"content": content, "mode": body.mode, "route": classification.route, "source": "session_graph.chat", "narration": narration},
        created_at=now,
    )
    graph.events.append(user_event)

    created_session: SessionRecord | None = None
    created_edge: SessionEdge | None = None
    extra_event: SessionEvent | None = None
    readiness_response: dict[str, object] | None = None
    assistant_turn: dict[str, object] | None = None
    chat_status = classification.route
    execution_state = classification.route

    if classification.route == "continue_active":
        created_session = _make_work_session(session, content, turn, now, context, body.mode, narration)
        created_session = _apply_repo_execution_metadata(created_session, session, graph.sessions)
        readiness_request = build_graph_work_execution_readiness_request(work_session=created_session, parent_session=session)
        start_callback = start_graph_workflow if readiness_request.worktree_id else None
        readiness_result = await ExecutionActivationService(start_workflow=start_callback).activate(readiness_request)
        created_session = record_execution_readiness_on_work_session(created_session, readiness_result)
        readiness_response = execution_readiness_response(readiness_result)
        if narration:
            readiness_response["narration"] = narration
        created_session.created_from_event_id = user_event.id
        graph.sessions.append(created_session)
        created_edge = SessionEdge(
            type=EdgeType.COMPONENT_OF,
            source_session_id=created_session.id,
            target_session_id=session.id,
            metadata={"reason": "Graph chat created a work session.", "source": classification.source, "narration": narration},
            created_at=now,
            created_from_event_id=user_event.id,
        )
        graph.edges.append(created_edge)
        execution_state = str(created_session.state.get("execution_state", "ready_for_execution"))
        readiness_auto_started = readiness_response.get("auto_started") is True
        execution_started = readiness_response.get("status") == "started" and readiness_auto_started
        extra_event = SessionEvent(
            type=SessionEventType.WORK_STARTED if execution_started else SessionEventType.WORK_EXECUTION_READINESS_RECORDED,
            session_id=created_session.id,
            root_session_id=created_session.root_id,
            actor=SessionEventActor.SYSTEM,
            data={
                "parent_session_id": session.id,
                "prompt": content,
                "requires_repo": not bool(session.metadata.get("repo_session_id")),
                "execution_state": execution_state,
                "auto_started": readiness_auto_started,
                "execution_readiness": readiness_response or {},
                "source": classification.source,
                "narration": narration,
            },
            created_at=now,
        )
        chat_status = "started" if execution_started else "needs_repo" if created_session.status == SessionStatus.BLOCKED else "ready"

    elif classification.route in {"create_child_goal", "create_sibling_goal"}:
        created_session = _make_goal_session(session, content, turn, now, context, classification.route)
        created_session.created_from_event_id = user_event.id
        graph.sessions.append(created_session)
        created_edge = SessionEdge(
            type=EdgeType.COMPONENT_OF if classification.route == "create_child_goal" else EdgeType.SIBLING_OF,
            source_session_id=created_session.id,
            target_session_id=session.id,
            metadata={"reason": classification.reason, "source": classification.source, "narration": narration},
            created_at=now,
            created_from_event_id=user_event.id,
        )
        graph.edges.append(created_edge)
        extra_event = SessionEvent(
            type=SessionEventType.GOAL_CREATED,
            session_id=created_session.id,
            root_session_id=created_session.root_id or created_session.id,
            actor=SessionEventActor.SYSTEM,
            data={"source_session_id": session.id, "route": classification.route, "prompt": content, "source": classification.source, "narration": narration},
            created_at=now,
        )

    elif classification.route == "question_only":
        answer = classification.assistant_response or "I can answer that, but I do not have a generated answer for this message yet."
        assistant_turn = {"role": "assistant", "content": answer, "created_at": now}
        turns.append(assistant_turn)
        session.state = {**session.state, "chat_turns": turns, "last_assistant_message": answer}
        graph.sessions[index] = session
        created_session = _make_chat_session(session, content, turn, assistant_turn, now, context, classification.source)
        created_session.created_from_event_id = user_event.id
        graph.sessions.append(created_session)
        created_edge = SessionEdge(
            type=EdgeType.COMPONENT_OF,
            source_session_id=created_session.id,
            target_session_id=session.id,
            metadata={"reason": classification.reason, "source": classification.source, "non_executable": True, "narration": narration},
            created_at=now,
            created_from_event_id=user_event.id,
        )
        graph.edges.append(created_edge)
        extra_event = SessionEvent(
            type=SessionEventType.OBSERVATION_RECORDED,
            session_id=created_session.id,
            root_session_id=created_session.root_id,
            actor=SessionEventActor.ASSISTANT,
            data={
                "route": classification.route,
                "reason": classification.reason,
                "source": classification.source,
                "assistant_response": answer,
                "response_session_kind": "chat",
                "auto_started": False,
                "narration": narration,
            },
            created_at=now,
        )
        chat_status = "answered"
        execution_state = "answered_inline"

    else:
        extra_event = SessionEvent(
            type=SessionEventType.OBSERVATION_RECORDED,
            session_id=session.id,
            root_session_id=session.root_id or session.id,
            actor=SessionEventActor.SYSTEM,
            data={"route": classification.route, "reason": classification.reason, "source": classification.source, "narration": narration},
            created_at=now,
        )

    if extra_event is not None:
        graph.events.append(extra_event)

    _save_or_400(store, graph)
    response: dict[str, object] = {
        "session": session.model_dump(mode="json"),
        "turn": turn,
        "routing_decision": {"route": classification.route, "reason": classification.reason, "source": classification.source, "narration": narration},
        "events": [event.model_dump(mode="json") for event in [user_event, extra_event] if event is not None],
        "chat_status": chat_status,
        "execution_state": execution_state,
        "auto_started": readiness_response.get("auto_started") if readiness_response else False,
        "narration": narration,
    }
    if assistant_turn is not None:
        response["assistant_turn"] = assistant_turn
        response["assistant_response"] = assistant_turn["content"]
    if readiness_response is not None:
        response["execution_readiness"] = readiness_response
    if created_session is not None:
        key = "work_session" if created_session.kind == SessionKind.WORK else "goal_session"
        if created_session.kind == SessionKind.CHAT:
            key = "chat_session"
        elif created_session.kind == SessionKind.QUESTION:
            key = "question_session"
        response[key] = created_session.model_dump(mode="json")
    if created_edge is not None:
        response["created_edge"] = created_edge.model_dump(mode="json")
    return response
