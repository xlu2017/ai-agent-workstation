"""Session CRUD routes (list, create, destroy, inspect, context)."""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from api.config import DEFAULT_MODEL, SESSIONS_DIR
from sessions.session_manager import (
    SessionAlreadyExists,
    SessionCreateRequest,
    SessionNotFound,
    create_session as create_session_record,
    destroy_session as destroy_session_record,
    get_session_context as get_session_context_record,
    inspect_session as inspect_session_record,
    list_sessions as list_session_records,
)

router = APIRouter(tags=["sessions"])

# Background task tracking
_running_tasks: dict[str, asyncio.Task] = {}


class SessionCreate(BaseModel):
    name: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    ports: Optional[str] = None
    profile: Optional[str] = None
    task: Optional[str] = None


class ChatMessage(BaseModel):
    instruction: str
    model: Optional[str] = None
    executor: Optional[str] = None
    execution_mode: Optional[str] = "finite"


@router.get("/api/sessions")
def list_sessions():
    return {"sessions": list_session_records()}


@router.post("/api/sessions")
def create_session(body: SessionCreate):
    try:
        return create_session_record(
            SessionCreateRequest(
                name=body.name,
                repo=body.repo,
                branch=body.branch,
                ports=body.ports,
                profile=body.profile,
                task=body.task,
            )
        )
    except SessionAlreadyExists as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/api/sessions/{session_id}")
def destroy_session(session_id: str):
    try:
        return destroy_session_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/sessions/{session_id}")
def inspect_session(session_id: str):
    try:
        return inspect_session_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/sessions/{session_id}/context")
def get_session_context(session_id: str):
    try:
        return get_session_context_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/sessions/{session_id}/state")
def get_session_state(session_id: str):
    from execution.prompt_handler import get_task_state
    return get_task_state(session_id)


@router.post("/api/sessions/{session_id}/interrupt")
async def session_interrupt(session_id: str):
    from execution.prompt_handler import _emit_event
    from execution.agentic_executor import _cancelled_sessions

    _cancelled_sessions.add(session_id)

    bg_task = _running_tasks.get(session_id)
    if not bg_task or bg_task.done():
        _running_tasks.pop(session_id, None)
        _cancelled_sessions.discard(session_id)
        return {"stopped": False, "message": "No active task to stop"}

    bg_task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass

    _running_tasks.pop(session_id, None)
    _cancelled_sessions.discard(session_id)
    _emit_event(session_id, "plan_cancelled", "Stopped by user", {
        "reason": "user_interrupt",
        "source": "stop_button",
    })
    return {"stopped": True, "message": "Task cancelled"}


@router.post("/api/sessions/{session_id}/chat")
async def session_chat(session_id: str, body: ChatMessage):
    from execution.prompt_handler import handle_prompt, TaskState
    import uuid as _uuid

    task_id = f"task-{_uuid.uuid4().hex[:12]}"

    existing = _running_tasks.get(session_id)
    if existing and not existing.done():
        return JSONResponse(
            status_code=409,
            content={"error": "A task is already running for this session", "session_id": session_id},
        )

    async def _run_in_background():
        try:
            result = await handle_prompt(
                session_id=session_id,
                instruction=body.instruction,
                model=body.model or DEFAULT_MODEL,
                execution_mode=body.execution_mode or "finite",
            )
            return result
        except asyncio.CancelledError:
            return None
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    bg_task = asyncio.create_task(_run_in_background())
    _running_tasks[session_id] = bg_task

    await asyncio.sleep(0.5)

    if bg_task.done():
        result = bg_task.result()
        if result:
            return {
                "task_id": result.task_id,
                "session_id": result.session_id,
                "state": result.state.value,
                "message": result.message,
                "routing_decision": getattr(result, "routing_decision", ""),
                "plan_summary": str(getattr(result, "plan_summary", ""))[:200],
                "error": getattr(result, "error", ""),
                "events_path": str(getattr(result, "events_path", "")),
                "metadata": getattr(result, "metadata", {}),
            }
        return {"task_id": task_id, "session_id": session_id, "state": "failed", "message": "Execution error"}

    return {
        "task_id": task_id,
        "session_id": session_id,
        "state": "working",
        "message": "Execution started. Poll events for progress.",
    }


@router.get("/api/sessions/{session_id}/chat/status")
async def session_chat_status(session_id: str):
    from execution.prompt_handler import TaskState
    bg_task = _running_tasks.get(session_id)
    if not bg_task:
        return {"state": "unknown", "message": "No active task"}
    if not bg_task.done():
        return {"state": "working", "message": "Still executing..."}
    result = bg_task.result()
    _running_tasks.pop(session_id, None)
    if not result:
        return {"state": "failed", "message": "Execution error"}
    return {
        "task_id": result.task_id,
        "session_id": result.session_id,
        "state": result.state.value,
        "message": result.message,
        "routing_decision": getattr(result, "routing_decision", ""),
        "plan_summary": str(getattr(result, "plan_summary", ""))[:200],
        "error": getattr(result, "error", ""),
    }


@router.get("/api/sessions/{session_id}/context/health")
def get_context_health_endpoint(session_id: str):
    from context_validator import get_context_health
    return get_context_health(session_id)


@router.post("/api/sessions/{session_id}/postmortem")
def generate_postmortem(session_id: str, reason: str = ""):
    from postmortem import Postmortem
    pm = Postmortem(session_id)
    return pm.generate(reason)
