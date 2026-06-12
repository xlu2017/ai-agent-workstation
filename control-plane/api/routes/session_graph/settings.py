"""Session graph settings and authorization routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.models.session_graph import SessionGraphSnapshot
from api.services.action_authorization import (
    ActionAuthorizationContext,
    ProposedAction,
    authorize_action,
)
from api.services.platform_settings import (
    AutomationSettings,
    ObservabilitySettings,
    get_automation_settings,
    get_observability_settings,
    update_automation_settings,
    update_observability_settings,
)
from api.services.session_graph_service import SessionGraphStore

router = APIRouter()


class AuthorizeActionRequest(BaseModel):
    action: ProposedAction
    context: ActionAuthorizationContext = ActionAuthorizationContext()
    graph: SessionGraphSnapshot | None = None


@router.get("/settings/observability")
def get_observability_settings_endpoint() -> dict[str, dict[str, object]]:
    return {"settings": get_observability_settings().model_dump(mode="json")}


@router.put("/settings/observability")
def update_observability_settings_endpoint(
    body: ObservabilitySettings,
) -> dict[str, dict[str, object]]:
    updated = update_observability_settings(body)
    return {"settings": updated.model_dump(mode="json")}


@router.get("/settings/automation")
def get_automation_settings_endpoint() -> dict[str, dict[str, object]]:
    return {"settings": get_automation_settings().model_dump(mode="json")}


@router.put("/settings/automation")
def update_automation_settings_endpoint(
    body: AutomationSettings,
) -> dict[str, dict[str, object]]:
    updated = update_automation_settings(body)
    return {"settings": updated.model_dump(mode="json")}


@router.post("/authorization/preview")
def preview_action_authorization_endpoint(
    body: AuthorizeActionRequest,
) -> dict[str, dict[str, object]]:
    """Preview whether one proposed action can run without chat confirmation.

    This endpoint is intentionally non-mutating. The execution loop should call
    this after schema validation and before executing an action. The UI can call
    it to explain why an action is automatic, confirmation-required, or blocked.
    """

    graph = body.graph or SessionGraphStore().load()
    try:
        result = authorize_action(body.action, graph, body.context)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"authorization": result.model_dump(mode="json")}
