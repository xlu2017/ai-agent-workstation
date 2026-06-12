"""Execution scaffold for app automation actions.

The scaffold is intentionally conservative: it performs catalog lookup, risk and
approval checks, and emits a normalized plan. Actual calls into vendored
runtimes are adapter-specific and should be wired per vendor after vendored
source is checked in and reviewed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.app_automation.models import AppAutomationExecuteRequest, AppAutomationExecuteResult
from api.app_automation.registry import get_action


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
        steps.append("Invoke vendored adapter runtime. This remains disabled until the runtime source is vendored and adapter-specific execution is wired.")
    return steps


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

    return AppAutomationExecuteResult(
        ok=False,
        status="adapter_not_wired",
        vendor=action.preferred_vendor,
        execution_kind=action.execution_kind,
        app_id=request.app_id,
        action_id=request.action_id,
        dry_run=False,
        message="Vendor source is present, but concrete execution wiring for this adapter is not implemented yet.",
        planned_steps=_planned_steps(action, request),
        event=event,
        error={"code": "ADAPTER_NOT_WIRED", "message": "Concrete vendored adapter execution is not implemented yet."},
    )
