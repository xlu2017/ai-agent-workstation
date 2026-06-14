"""Session graph canonical action routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.routes.session_graph.helpers import RequestContext, _context, _get_visible_session, _store
from api.services.session_action_catalog import (
    execute_session_action_async,
    get_session_action,
    session_action_catalog,
    validate_session_action_params,
)

router = APIRouter()


class SessionActionRequest(BaseModel):
    action_name: str
    params: dict[str, object] = Field(default_factory=dict)
    preview: bool = False


@router.get("/actions")
def list_session_graph_actions() -> dict[str, object]:
    return session_action_catalog()


@router.get("/actions/{action_name}")
def get_session_graph_action(action_name: str) -> dict[str, object]:
    action = get_session_action(action_name)
    if action is None:
        raise HTTPException(404, f"Unknown session graph action: {action_name}")
    return {"action": action}


@router.post("/actions/validate")
def validate_session_graph_action(body: SessionActionRequest) -> dict[str, object]:
    return validate_session_action_params(body.action_name, body.params)


@router.post("/actions/apply")
async def apply_session_graph_action(body: SessionActionRequest, context: RequestContext = Depends(_context)) -> dict[str, object]:
    store = _store()
    _assert_action_sessions_visible(body.action_name, body.params, store, context)
    try:
        return await execute_session_action_async(store, body.action_name, body.params, preview=body.preview)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _assert_action_sessions_visible(action_name: str, params: dict[str, object], store, context: RequestContext) -> None:
    validation = validate_session_action_params(action_name, params)
    if not validation["ok"]:
        raise HTTPException(400, str(validation["error"]))
    for key in ("source_session_id", "target_session_id"):
        value = params.get(key)
        if isinstance(value, str):
            _get_visible_session(store, value, context)
