from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ambient.config import get_ambient_config
from ambient.context_packet import build_context_packet
from ambient.collectors.editor_bridge import build_editor_selection_event
from ambient.collectors.terminal_collector import TerminalObservationBuilder
from ambient.event_log import load_ambient_events, persist_ambient_event
from ambient.evidence_graph import write_evidence_graph
from ambient.reducers import reduce_ambient_events
from ambient.service import AmbientObservationService
from ambient.types import AmbientEvent
from ambient.vendor_registry import ambient_vendor_status

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))

router = APIRouter(prefix="/api/sessions/{session_id}/ambient", tags=["ambient-context"])


class AmbientCollectRequest(BaseModel):
    goal: str | None = None


class TerminalCommandStartedRequest(BaseModel):
    terminal_id: str = "default"
    cwd: str = ""
    command: str
    repo_id: str | None = None
    worktree_id: str | None = None
    branch: str | None = None


class TerminalCommandCompletedRequest(BaseModel):
    terminal_id: str = "default"
    cwd: str = ""
    command: str
    exit_code: int
    duration_ms: int | None = None
    stdout: str = ""
    stderr: str = ""
    repo_id: str | None = None
    worktree_id: str | None = None
    branch: str | None = None
    extra: dict[str, Any] | None = None


class EditorSelectionRequest(BaseModel):
    path: str
    start_line: int
    end_line: int
    selected_text: str = ""
    symbol: str | None = None
    diagnostics: list[dict[str, Any]] | None = None
    repo_id: str | None = None
    worktree_id: str | None = None
    branch: str | None = None
    confidence: float = 0.95


def _persist_and_refresh(session_id: str, event: AmbientEvent) -> AmbientEvent:
    if event.session_id != session_id:
        event.session_id = session_id
    stored = persist_ambient_event(event, sessions_dir=SESSIONS_DIR)
    events = load_ambient_events(session_id, sessions_dir=SESSIONS_DIR)
    write_evidence_graph(events, sessions_dir=SESSIONS_DIR)
    return stored


@router.get("/vendors")
def get_ambient_vendors(session_id: str):
    """Return ambient vendor/provider status for this control-plane instance."""

    status = ambient_vendor_status()
    status["session_id"] = session_id
    return status


@router.post("/events")
def ingest_ambient_event(session_id: str, event: AmbientEvent):
    """Ingest one structured ambient context event for a session."""

    stored = _persist_and_refresh(session_id, event)
    return {"ok": True, "event": stored.model_dump()}


@router.post("/terminal/started")
def ingest_terminal_command_started(session_id: str, body: TerminalCommandStartedRequest):
    """Replacement for legacy terminal watcher command-start telemetry."""

    event = TerminalObservationBuilder().command_started(
        session_id,
        terminal_id=body.terminal_id,
        cwd=body.cwd,
        command=body.command,
        repo_id=body.repo_id,
        worktree_id=body.worktree_id,
        branch=body.branch,
    )
    stored = _persist_and_refresh(session_id, event)
    return {"ok": True, "event": stored.model_dump()}


@router.post("/terminal/completed")
def ingest_terminal_command_completed(session_id: str, body: TerminalCommandCompletedRequest):
    """Replacement for legacy terminal watcher command-completion/error telemetry."""

    event = TerminalObservationBuilder().command_completed(
        session_id,
        terminal_id=body.terminal_id,
        cwd=body.cwd,
        command=body.command,
        exit_code=body.exit_code,
        duration_ms=body.duration_ms,
        stdout=body.stdout,
        stderr=body.stderr,
        repo_id=body.repo_id,
        worktree_id=body.worktree_id,
        branch=body.branch,
        extra=body.extra,
    )
    stored = _persist_and_refresh(session_id, event)
    return {"ok": True, "event": stored.model_dump()}


@router.post("/editor/selection")
def ingest_editor_selection(session_id: str, body: EditorSelectionRequest):
    """Replacement for legacy /editor-context bridge messages."""

    event = build_editor_selection_event(
        session_id,
        path=body.path,
        start_line=body.start_line,
        end_line=body.end_line,
        selected_text=body.selected_text,
        symbol=body.symbol,
        diagnostics=body.diagnostics,
        repo_id=body.repo_id,
        worktree_id=body.worktree_id,
        branch=body.branch,
        confidence=body.confidence,
    )
    stored = _persist_and_refresh(session_id, event)
    return {"ok": True, "event": stored.model_dump()}


@router.post("/collect")
def collect_ambient_context(session_id: str, body: AmbientCollectRequest | None = None):
    """Run one resilient ambient collection pass for a session."""

    result = AmbientObservationService(get_ambient_config()).collect_once(
        session_id=session_id,
        goal=body.goal if body else None,
    )
    return result.model_dump()


@router.get("/events")
def list_ambient_events(session_id: str, limit: int = 200):
    events = load_ambient_events(session_id, sessions_dir=SESSIONS_DIR, limit=limit)
    return {"session_id": session_id, "events": [event.model_dump() for event in events], "total": len(events)}


@router.get("/state")
def get_ambient_state(session_id: str, limit: int = 500, collect: bool = Query(False)):
    if collect:
        AmbientObservationService(get_ambient_config()).collect_once(session_id=session_id)
    events = load_ambient_events(session_id, sessions_dir=SESSIONS_DIR, limit=limit)
    state = reduce_ambient_events(events)
    return state.model_dump()


@router.get("/context")
def get_ambient_context_packet(session_id: str, goal: str | None = None, limit: int = 500, collect: bool = Query(False)):
    if collect:
        AmbientObservationService(get_ambient_config()).collect_once(session_id=session_id, goal=goal)
    events = load_ambient_events(session_id, sessions_dir=SESSIONS_DIR, limit=limit)
    packet = build_context_packet(session_id=session_id, events=events, goal=goal)
    return packet.model_dump()


@router.get("/health")
def get_ambient_health(session_id: str):
    return AmbientObservationService(get_ambient_config()).health(session_id=session_id)
