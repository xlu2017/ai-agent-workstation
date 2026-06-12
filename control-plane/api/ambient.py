from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ambient.config import get_ambient_config
from ambient.context_packet import build_context_packet
from ambient.event_log import load_ambient_events, persist_ambient_event
from ambient.evidence_graph import write_evidence_graph
from ambient.reducers import reduce_ambient_events
from ambient.service import AmbientObservationService
from ambient.types import AmbientEvent

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))

router = APIRouter(prefix="/api/sessions/{session_id}/ambient", tags=["ambient-context"])


class AmbientCollectRequest(BaseModel):
    goal: str | None = None


@router.post("/events")
def ingest_ambient_event(session_id: str, event: AmbientEvent):
    """Ingest one structured ambient context event for a session."""

    if event.session_id != session_id:
        event.session_id = session_id
    stored = persist_ambient_event(event, sessions_dir=SESSIONS_DIR)
    events = load_ambient_events(session_id, sessions_dir=SESSIONS_DIR)
    write_evidence_graph(events, sessions_dir=SESSIONS_DIR)
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
