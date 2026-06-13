"""Execution scaffold for app automation actions.

The executor performs catalog lookup, approval checks, routing across the vendor
ladder, and normalized planning. Live vendor runtime calls remain behind the
platform-owned adapter boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.app_automation.adapter_base import VendorAdapter
from api.app_automation.models import AppAutomationExecuteRequest, AppAutomationExecuteResult
from api.app_automation.registry import CONTROL_PLANE_ROOT, get_action, list_vendor_tools
from api.app_automation.vendor_plan import build_action_plan


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _planned_steps(action, request: AppAutomationExecuteRequest, route_plan: dict[str, Any] | None = None) -> list[str]:
    steps = [
        f"Resolve action {action.id} for app {action.app_id}.",
        f"Build route plan across API, MCP, workflow, browser, visual browser, and desktop layers.",
        f"Validate parameters against action schema keys: {', '.join(action.input_schema.get('properties', {}).keys())}.",
    ]
    if route_plan:
        candidates = route_plan.get("candidates", [])
        labels = [f"{item.get('rank')}. {item.get('vendor')} ({item.get('layer')}, {item.get('status')})" for item in candidates]
        if labels:
            steps.append("Candidate vendor ladder: " + "; ".join(labels))
        if route_plan.get("selected_vendor"):
            steps.append(f"Select {route_plan.get('selected_vendor')} at layer {route_plan.get('selected_layer')}.")
    if action.approval == "required" and not request.approval_granted:
        steps.append("Stop before execution because approval is required.")
    elif request.dry_run:
        steps.append("Stop before execution because dry_run=true.")
    else:
        steps.append("Invoke the committed vendored-source adapter scaffold.")
    return steps


def _source_path_for_vendor(vendor_id: str):
    for tool in list_vendor_tools():
        if tool.id == vendor_id:
            return CONTROL_PLANE_ROOT.parent / tool.target_dir
    return None


def _adapter_for_vendor(vendor_id: str | None) -> VendorAdapter | None:
    if not vendor_id:
        return None
    source_path = _source_path_for_vendor(vendor_id)
    if source_path is None:
        return None
    adapter = VendorAdapter(source_path)
    adapter.vendor_id = vendor_id
    return adapter


def _selected_candidate_installed(route_plan: dict[str, Any]) -> bool:
    selected = route_plan.get("selected_vendor")
    for candidate in route_plan.get("candidates", []):
        if candidate.get("vendor") == selected:
            return bool(candidate.get("installed"))
    return False


def execute_app_action(request: AppAutomationExecuteRequest) -> AppAutomationExecuteResult:
    action = get_action(request.action_id)
    if not action or action.app_id != request.app_id:
        return AppAutomationExecuteResult(
            ok=False,
            status="unknown_action",
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=request.dry_run,
            message=f"Unknown app action: {request.app_id}/{request.action_id}",
            error={"code": "UNKNOWN_ACTION", "message": f"Unknown app action: {request.app_id}/{request.action_id}"},
        )

    route_plan = build_action_plan(action)
    selected_vendor = route_plan.get("selected_vendor") or action.preferred_vendor
    selected_layer = route_plan.get("selected_layer") or action.execution_kind
    required_approval = action.approval == "required" and not request.approval_granted
    event = {
        "event_type": "app_automation_planned",
        "timestamp": _now(),
        "session_id": request.session_id,
        "app_id": request.app_id,
        "action_id": request.action_id,
        "vendor": selected_vendor,
        "preferred_vendor": action.preferred_vendor,
        "execution_kind": selected_layer,
        "risk": action.risk,
        "dry_run": request.dry_run,
        "route_candidates": route_plan.get("candidates", []),
        "params_preview": {key: str(value)[:120] for key, value in request.params.items()},
    }

    if required_approval:
        return AppAutomationExecuteResult(
            ok=True,
            status="needs_approval",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=request.dry_run,
            required_approval=True,
            message=f"{action.label} requires approval before execution.",
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=event,
        )

    if request.dry_run:
        return AppAutomationExecuteResult(
            ok=True,
            status="planned",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=True,
            message=f"Dry run planned for {action.label} via {selected_vendor}.",
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=event,
        )

    if not _selected_candidate_installed(route_plan):
        return AppAutomationExecuteResult(
            ok=False,
            status="vendor_not_installed",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=False,
            message=f"No installed vendor source is available for action {action.id}.",
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=event,
            error={"code": "VENDOR_NOT_INSTALLED", "message": f"No installed vendor source is available for action {action.id}."},
        )

    adapter = _adapter_for_vendor(selected_vendor)
    if adapter is None:
        return AppAutomationExecuteResult(
            ok=False,
            status="adapter_missing",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=False,
            message="No platform adapter scaffold is registered for this vendor.",
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=event,
            error={"code": "ADAPTER_MISSING", "message": "No adapter scaffold is registered."},
        )

    adapter_result = adapter.execute(action, request)
    return AppAutomationExecuteResult(
        ok=adapter_result.ok,
        status=adapter_result.status,
        vendor=selected_vendor,
        execution_kind=action.execution_kind,
        app_id=request.app_id,
        action_id=request.action_id,
        dry_run=False,
        message=adapter_result.message,
        planned_steps=[*_planned_steps(action, request, route_plan), *adapter_result.planned_steps],
        route_plan=route_plan,
        event={**event, "adapter_status": adapter_result.status},
        error=adapter_result.error,
    )
