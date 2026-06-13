"""Execution scaffold for app automation actions.

The executor performs catalog lookup, approval checks, and normalized planning.
When a vendored source tree is present it now returns a vendor-specific scaffold
plan instead of treating the provider as missing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api.app_automation.adapter_base import VendorAdapter
from api.app_automation.models import AppAutomationExecuteRequest, AppAutomationExecuteResult
from api.app_automation.registry import CONTROL_PLANE_ROOT, get_action, list_vendor_tools


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _planned_steps(action, request: AppAutomationExecuteRequest) -> list[str]:
    steps = [
        f"Resolve action {action.id} for app {action.app_id}.",
        f"Select preferred vendor {action.preferred_vendor} with execution kind {action.execution_kind}.",
        f"Validate parameters against action schema keys: {', '.join(action.input_schema.get('properties', {}).keys())}.",
    ]
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


def _adapter_for(action) -> VendorAdapter | None:
    source_path = _source_path_for_vendor(action.preferred_vendor)
    if source_path is None:
        return None
    adapter = VendorAdapter(source_path)
    adapter.vendor_id = action.preferred_vendor
    return adapter


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

    required_approval = action.approval == "required" and not request.approval_granted
    event = {
        "event_type": "app_automation_planned",
        "timestamp": _now(),
        "session_id": request.session_id,
        "app_id": request.app_id,
        "action_id": request.action_id,
        "vendor": action.preferred_vendor,
        "execution_kind": action.execution_kind,
        "risk": action.risk,
        "dry_run": request.dry_run,
        "params_preview": {key: str(value)[:120] for key, value in request.params.items()},
    }

    if required_approval:
        return AppAutomationExecuteResult(
            ok=True,
            status="needs_approval",
            vendor=action.preferred_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=request.dry_run,
            required_approval=True,
            message=f"{action.label} requires approval before execution.",
            planned_steps=_planned_steps(action, request),
            event=event,
        )

    if request.dry_run:
        return AppAutomationExecuteResult(
            ok=True,
            status="planned",
            vendor=action.preferred_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=True,
            message=f"Dry run planned for {action.label} via {action.preferred_vendor}.",
            planned_steps=_planned_steps(action, request),
            event=event,
        )

    if not action.available:
        return AppAutomationExecuteResult(
            ok=False,
            status="vendor_not_installed",
            vendor=action.preferred_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=False,
            message=action.unavailable_reason,
            planned_steps=_planned_steps(action, request),
            event=event,
            error={"code": "VENDOR_NOT_INSTALLED", "message": action.unavailable_reason},
        )

    adapter = _adapter_for(action)
    if adapter is None:
        return AppAutomationExecuteResult(
            ok=False,
            status="adapter_missing",
            vendor=action.preferred_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=False,
            message="No platform adapter scaffold is registered for this vendor.",
            planned_steps=_planned_steps(action, request),
            event=event,
            error={"code": "ADAPTER_MISSING", "message": "No adapter scaffold is registered."},
        )

    adapter_result = adapter.execute(action, request)
    return AppAutomationExecuteResult(
        ok=adapter_result.ok,
        status=adapter_result.status,
        vendor=action.preferred_vendor,
        execution_kind=action.execution_kind,
        app_id=request.app_id,
        action_id=request.action_id,
        dry_run=False,
        message=adapter_result.message,
        planned_steps=[*_planned_steps(action, request), *adapter_result.planned_steps],
        event={**event, "adapter_status": adapter_result.status},
        error=adapter_result.error,
    )
