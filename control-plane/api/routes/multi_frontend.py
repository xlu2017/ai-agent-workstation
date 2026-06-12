from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.models.multi_frontend import (
    CreateMultiFrontendTopologyRequest,
    RegisterCrossClientTraceRequest,
)
from api.services.multi_frontend_session_controller import MultiFrontendSessionController


router = APIRouter(prefix="/api/multi-frontend", tags=["multi-frontend"])


def _controller() -> MultiFrontendSessionController:
    return MultiFrontendSessionController()


@router.post("/topologies")
def create_topology(body: CreateMultiFrontendTopologyRequest) -> dict[str, object]:
    """Create one app session, one shared backend session, and many frontend client sessions."""
    try:
        topology = _controller().create_topology(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"topology": topology.model_dump(mode="json")}


@router.get("/topologies/{root_session_id}")
def get_topology(root_session_id: str) -> dict[str, object]:
    try:
        topology = _controller().get_topology(root_session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"topology": topology.model_dump(mode="json")}


@router.get("/topologies/{root_session_id}/matrix")
def get_matrix(root_session_id: str) -> dict[str, object]:
    try:
        matrix = _controller().matrix(root_session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"matrix": matrix.model_dump(mode="json")}


@router.get("/topologies/{root_session_id}/frontends/{frontend_instance_id}/trace-headers")
def get_trace_headers(
    root_session_id: str,
    frontend_instance_id: str,
    user_flow_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, object]:
    try:
        headers = _controller().build_trace_headers(
            root_session_id=root_session_id,
            frontend_instance_id=frontend_instance_id,
            user_flow_id=user_flow_id,
            trace_id=trace_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "headers": {
            "x-agent-root-session-id": headers.root_session_id,
            "x-agent-backend-session-id": headers.backend_session_id,
            "x-agent-frontend-session-id": headers.frontend_session_id,
            "x-agent-frontend-instance-id": headers.frontend_instance_id,
            "x-agent-device-profile-id": headers.device_profile_id,
            "x-agent-user-flow-id": headers.user_flow_id,
            "x-agent-trace-id": headers.trace_id,
        },
        "correlation": headers.model_dump(mode="json"),
    }


@router.post("/traces")
def register_trace(body: RegisterCrossClientTraceRequest) -> dict[str, object]:
    try:
        trace = _controller().register_trace(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"trace": trace.model_dump(mode="json")}
