"""App automation catalog and execution routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.app_automation.executor import execute_app_action
from api.app_automation.models import AppAutomationExecuteRequest
from api.app_automation.registry import list_actions, load_manifest, vendor_status

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
    }


@router.get("/actions")
def app_automation_actions(app_id: str | None = None) -> dict:
    """Return normalized app actions across API/MCP/workflow/browser vendors."""
    actions = list_actions()
    if app_id:
        actions = [action for action in actions if action.app_id == app_id]
    return {"actions": [action.model_dump() for action in actions]}


@router.post("/execute")
def app_automation_execute(body: AppAutomationExecuteRequest) -> dict:
    """Plan or execute an app action.

    Currently executes the safe end-to-end scaffold: lookup, risk/approval gate,
    dry-run planning, and vendor availability checks. Concrete runtime invocation
    is intentionally blocked until vendored source is present and adapter wiring
    is explicitly reviewed.
    """
    result = execute_app_action(body)
    return result.model_dump()
