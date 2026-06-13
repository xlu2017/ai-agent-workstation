"""App automation catalog, runtime configuration, and execution routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.app_automation.config import (
    AppAutomationVendorConfigInput,
    all_vendor_config_status,
    clear_vendor_config,
    save_vendor_config,
    vendor_config_status,
)
from api.app_automation.event_log import list_app_automation_events
from api.app_automation.executor import execute_app_action
from api.app_automation.models import AppAutomationExecuteRequest
from api.app_automation.registry import get_action, list_actions, load_manifest, vendor_status
from api.app_automation.vendor_plan import build_action_plan, vendor_profile_matrix

router = APIRouter(prefix="/api/app-automation", tags=["app-automation"])


@router.get("/vendors")
def app_automation_vendors() -> dict:
    """Return selected vendored automation tools and install/configuration status."""
    manifest = load_manifest()
    config_by_vendor = {item["vendor_id"]: item for item in all_vendor_config_status()["vendors"]}
    vendors = []
    for vendor in vendor_status():
        vendors.append({
            **vendor,
            "runtime_config": config_by_vendor.get(vendor["id"]),
        })
    return {
        "version": manifest.get("version", 1),
        "default_execution_ladder": manifest.get("default_execution_ladder", []),
        "seed_apps": manifest.get("seed_apps", []),
        "vendors": vendors,
        "capability_matrix": vendor_profile_matrix(),
    }


@router.get("/config")
def app_automation_config() -> dict:
    """Return redacted runtime configuration status for configurable vendors."""
    return all_vendor_config_status()


@router.get("/config/{vendor_id}")
def app_automation_vendor_config(vendor_id: str) -> dict:
    """Return redacted runtime configuration status for one vendor."""
    try:
        return vendor_config_status(vendor_id)
    except Exception as exc:  # pragma: no cover - defensive route boundary
        raise HTTPException(status_code=404, detail=f"Unknown vendor: {vendor_id}") from exc


@router.put("/config/{vendor_id}")
def update_app_automation_vendor_config(vendor_id: str, body: AppAutomationVendorConfigInput) -> dict:
    """Persist endpoint/command configuration for one vendor runtime."""
    try:
        return save_vendor_config(vendor_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown vendor: {vendor_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/config/{vendor_id}")
def delete_app_automation_vendor_config(vendor_id: str) -> dict:
    """Clear stored runtime configuration for one vendor."""
    try:
        return clear_vendor_config(vendor_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown vendor: {vendor_id}") from exc


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


@router.get("/events/{session_id}")
def app_automation_events(session_id: str, limit: int = 200) -> dict:
    """Return app-automation audit events recorded for a session."""
    safe_limit = max(1, min(limit, 1000))
    events = list_app_automation_events(session_id, limit=safe_limit)
    return {"session_id": session_id, "events": events, "count": len(events)}


@router.post("/execute")
def app_automation_execute(body: AppAutomationExecuteRequest) -> dict:
    """Plan or execute an app action."""
    result = execute_app_action(body)
    return result.model_dump()
