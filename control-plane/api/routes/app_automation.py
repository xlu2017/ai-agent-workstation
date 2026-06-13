"""App automation catalog and execution routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.app_automation.executor import execute_app_action
from api.app_automation.models import AppAutomationExecuteRequest
from api.app_automation.registry import get_action, list_actions, load_manifest, vendor_status
from api.app_automation.vendor_plan import build_action_plan, vendor_profile_matrix

router = APIRouter(prefix="/api/app-automation", tags=["app-automation"])


@router.get("/vendors")
def app_automation_vendors() -> dict:
    """Return selected vendored automation tools and install status."""
    manifest = load_manifest()
    return {
        "version": manifest.get("version", 1),
        "default_execution_ladder": manifest.get("default_execution_ladder", []),
        "seed_apps": manifest.get("seed_apps", []),
        "vendors": vendor_status(),
        "capability_matrix": vendor_profile_matrix(),
    }


@router.get("/capabilities")
def app_automation_capabilities() -> dict:
    """Return how the app automation vendors cooperate by layer."""
    return {"capability_matrix": vendor_profile_matrix()}


@router.get("/actions")
def app_automation_actions(app_id: str | None = None) -> dict:
    """Return normalized app actions across API/MCP/workflow/browser vendors."""
    actions = list_actions()
    if app_id:
        actions = [action for action in actions if action.app_id == app_id]
    return {"actions": [action.model_dump() for action in actions]}


@router.get("/actions/{action_id}/plan")
def app_automation_action_plan(action_id: str) -> dict:
    """Return the vendor route plan for one action."""
    action = get_action(action_id)
    if not action:
        return {"ok": False, "error": {"code": "UNKNOWN_ACTION", "message": f"Unknown app action: {action_id}"}}
    return {"ok": True, "plan": build_action_plan(action)}


@router.post("/execute")
def app_automation_execute(body: AppAutomationExecuteRequest) -> dict:
    """Plan or execute an app action."""
    result = execute_app_action(body)
    return result.model_dump()
