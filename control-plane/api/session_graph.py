from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.models.session_graph import (
    ContextProjection,
    MountSessionRequest,
    MountSessionResult,
    SessionEdge,
    SessionGraphSnapshot,
    SessionRecord,
    SessionUpdateProposal,
)
from api.services.session_adapter_engine import adapt_session, mount_session, preview_mount_session
from api.services.session_graph_service import SessionGraphStore


router = APIRouter(prefix="/api/session-graph", tags=["session-graph"])


def _store() -> SessionGraphStore:
    return SessionGraphStore()


@router.get("/sessions")
def list_sessions() -> dict[str, list[dict[str, object]]]:
    return {"sessions": [session.model_dump(mode="json") for session in _store().list_sessions()]}


@router.post("/sessions")
def create_session(body: SessionRecord) -> dict[str, dict[str, object]]:
    return {"session": _store().create_session(body).model_dump(mode="json")}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, dict[str, object]]:
    session = _store().get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    return {"session": session.model_dump(mode="json")}


@router.get("/edges")
def list_session_edges(session_id: str | None = Query(None)) -> dict[str, list[dict[str, object]]]:
    return {"edges": [edge.model_dump(mode="json") for edge in _store().list_edges(session_id)]}


@router.post("/mount")
def mount_session_endpoint(body: MountSessionRequest) -> dict[str, dict[str, object]]:
    try:
        result = mount_session(_store(), body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.post("/adapt")
def adapt_session_endpoint(body: MountSessionRequest) -> dict[str, dict[str, object]]:
    try:
        session = adapt_session(_store(), body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"session": session.model_dump(mode="json")}


@router.post("/mount/preview")
def preview_mount_endpoint(body: MountSessionRequest) -> dict[str, dict[str, object]]:
    try:
        result = preview_mount_session(_store(), body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.get("/context-projection/{session_id}")
def get_context_projection(session_id: str) -> dict[str, dict[str, object]]:
    projection = _store().get_projection_for(session_id)
    if projection is None:
        raise HTTPException(404, f"Context projection for {session_id} not found")
    return {"projection": projection.model_dump(mode="json")}


@router.post("/session-update/apply")
def apply_session_update(body: SessionUpdateProposal) -> dict[str, dict[str, object]]:
    try:
        graph = _store().apply_update_proposal(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"graph": graph.model_dump(mode="json")}


@router.get("/snapshot")
def get_snapshot() -> dict[str, dict[str, object]]:
    return {"graph": _store().load().model_dump(mode="json")}
