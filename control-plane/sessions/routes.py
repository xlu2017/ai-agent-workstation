"""
API routes for session management, prompt intake, and control commands.

Endpoints:
  POST /api/v2/sessions                       — create a session
  GET  /api/v2/sessions                       — list sessions
  GET  /api/v2/sessions/{id}                  — get session details
  POST /api/v2/sessions/{id}/prompts          — submit a prompt
  POST /api/v2/sessions/{id}/control          — pause/resume/cancel
  GET  /api/v2/sessions/{id}/events/stream    — SSE live feed
  GET  /api/v2/sessions/{id}/events           — paginated events
  GET  /api/v2/sessions/{id}/concurrency      — worktree claim info

v2 prefix keeps these separate from the existing /api/sessions in server.py.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from live_feed.events import EventStore, EventType, create_event
from sessions.controller import (
    ControlRequest,
    CreateSessionRequest,
    PromptRequest,
    SessionController,
)
from sessions.concurrency import ConcurrencyManager
from sessions.models import SessionStatus, SessionStore, SessionType

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))

router = APIRouter(prefix="/api/v2")

# Shared instances — created once, used by all requests
_controller: SessionController | None = None
_concurrency: ConcurrencyManager | None = None


def _get_controller() -> SessionController:
    global _controller
    if _controller is None:
        _controller = SessionController(str(SESSIONS_DIR))
    return _controller


def _get_concurrency() -> ConcurrencyManager:
    global _concurrency
    if _concurrency is None:
        store = SessionStore(str(SESSIONS_DIR))
        _concurrency = ConcurrencyManager(store)
    return _concurrency


# ── Session CRUD ──────────────────────────────────────────────────

@router.post("/sessions")
async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    """Create a new session.

    Session types: root_session, child_session, parallel_session, queued_session
    """
    ctrl = _get_controller()
    return ctrl.create_session(body)


@router.get("/sessions")
async def list_sessions(
    parent_id: str | None = Query(None),
    status: str | None = Query(None),
    session_type: str | None = Query(None),
) -> dict[str, Any]:
    """List sessions with optional filters."""
    store = SessionStore(str(SESSIONS_DIR))
    status_filter = SessionStatus(status) if status else None
    type_filter = SessionType(session_type) if session_type else None
    sessions = store.list_sessions(
        parent_id=parent_id,
        status=status_filter,
        session_type=type_filter,
    )
    return {"sessions": [s.to_dict() for s in sessions]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """Get session details."""
    store = SessionStore(str(SESSIONS_DIR))
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    return {"session": session.to_dict()}


# ── Prompt intake ─────────────────────────────────────────────────

@router.post("/sessions/{session_id}/prompts")
async def submit_prompt(
    session_id: str, body: PromptRequest
) -> dict[str, Any]:
    """Submit a prompt while work may be running.

    The platform routes the prompt to: append_to_current, modify_current_plan,
    interrupt_current, spawn_child_session, spawn_new_session, or queue.
    """
    ctrl = _get_controller()
    result = ctrl.handle_prompt(session_id, body)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# ── Control commands ──────────────────────────────────────────────

@router.post("/sessions/{session_id}/control")
async def control_session(
    session_id: str, body: ControlRequest
) -> dict[str, Any]:
    """Send a control command: pause, resume, cancel, commit_checkpoint."""
    ctrl = _get_controller()
    result = ctrl.handle_control(session_id, body)
    if "error" in result:
        raise HTTPException(404 if "not found" in result["error"] else 400, result["error"])
    return result


# ── Event stream (SSE) ───────────────────────────────────────────

async def _event_generator(
    store: EventStore,
    session_id: str,
    after_sequence: int = 0,
    poll_interval: float = 0.5,
):
    """Yield SSE-formatted events as they appear."""
    last_seq = after_sequence
    heartbeat_counter = 0

    while True:
        events = store.get_events(session_id, after_sequence=last_seq, limit=100)
        if events:
            heartbeat_counter = 0
            for evt in events:
                last_seq = evt.get("sequence", last_seq)
                event_type = evt.get("event_type", "message")
                event_id = evt.get("event_id", "")
                yield f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(evt)}\n\n"
        else:
            heartbeat_counter += 1
            if heartbeat_counter % 30 == 0:
                yield f": heartbeat {heartbeat_counter}\n\n"

        await asyncio.sleep(poll_interval)


@router.get("/sessions/{session_id}/events/stream")
async def stream_events(
    session_id: str,
    after_sequence: int = Query(0),
) -> StreamingResponse:
    """SSE endpoint for live session event streaming.

    Connect with EventSource:
        const es = new EventSource('/api/v2/sessions/my-session/events/stream');
        es.addEventListener('action_completed', (e) => { ... });
    """
    store = EventStore(str(SESSIONS_DIR))
    return StreamingResponse(
        _event_generator(store, session_id, after_sequence),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}/events")
async def get_events(
    session_id: str,
    after_sequence: int = Query(0),
    event_type: str | None = Query(None),
    limit: int = Query(100, le=1000),
) -> dict[str, Any]:
    """Get events for a session (non-streaming, paginated)."""
    store = EventStore(str(SESSIONS_DIR))
    type_filter = None
    if event_type:
        try:
            type_filter = [EventType(event_type)]
        except ValueError:
            pass
    events = store.get_events(
        session_id,
        after_sequence=after_sequence,
        event_types=type_filter,
        limit=limit,
    )
    return {"session_id": session_id, "events": events, "count": len(events)}


# ── Concurrency info ─────────────────────────────────────────────

@router.get("/sessions/{session_id}/concurrency")
async def get_concurrency_info(session_id: str) -> dict[str, Any]:
    """Get worktree claim information for this session."""
    mgr = _get_concurrency()
    claims = mgr.get_active_claims()
    session_claims = {
        wt: info for wt, info in claims.items() if info["session_id"] == session_id
    }
    return {"session_id": session_id, "claims": session_claims, "all_claims": claims}


class WorktreeClaimRequest(BaseModel):
    worktree_id: str
    mode: str = "mutating"
    files: list[str] = []


@router.post("/sessions/{session_id}/concurrency/claim")
async def claim_worktree(
    session_id: str, body: WorktreeClaimRequest
) -> dict[str, Any]:
    """Claim a worktree for this session."""
    mgr = _get_concurrency()
    result = mgr.claim_worktree(
        session_id, body.worktree_id, body.mode, body.files
    )
    if not result.allowed:
        raise HTTPException(409, result.reason)
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "worktree_id": result.worktree_id,
    }


@router.post("/sessions/{session_id}/concurrency/release")
async def release_worktree(
    session_id: str, body: WorktreeClaimRequest
) -> dict[str, Any]:
    """Release a worktree claim."""
    mgr = _get_concurrency()
    released = mgr.release_worktree(session_id, body.worktree_id)
    return {"released": released, "worktree_id": body.worktree_id}
