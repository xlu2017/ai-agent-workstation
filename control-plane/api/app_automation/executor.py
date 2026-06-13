"""Execution scaffold for app automation actions.

The executor performs catalog lookup, parameter contract validation, approval
checks, routing across the vendor ladder, normalized planning, event logging,
and runtime adapter dispatch. Live vendor calls remain behind the platform-owned
adapter boundary.
"""

from __future__ import annotations

from typing import Any

from live_feed.events import EventType

from api.app_automation.adapter_base import VendorAdapter
from api.app_automation.event_log import emit_app_automation_event, redact_sensitive
from api.app_automation.models import AppAutomationExecuteRequest, AppAutomationExecuteResult
from api.app_automation.registry import CONTROL_PLANE_ROOT, get_action, list_vendor_tools
from api.app_automation.vendor_plan import build_action_plan


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


def _make_base_event(action, request: AppAutomationExecuteRequest, route_plan: dict[str, Any], selected_vendor: str | None, selected_layer: str | None) -> dict[str, Any]:
    return {
        "app_id": request.app_id,
        "action_id": request.action_id,
        "vendor": selected_vendor,
        "preferred_vendor": action.preferred_vendor,
        "execution_kind": selected_layer,
        "risk": action.risk,
        "approval": action.approval,
        "dry_run": request.dry_run,
        "approval_granted": request.approval_granted,
        "route_candidates": route_plan.get("candidates", []),
        "params_preview": redact_sensitive({key: str(value)[:120] for key, value in request.params.items()}),
    }


def _schema_type_matches(expected_type: str | None, value: Any) -> bool:
    if expected_type is None:
        return True
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _validate_params(action, params: dict[str, Any]) -> dict[str, Any] | None:
    schema = action.input_schema or {}
    properties = schema.get("properties", {}) if isinstance(schema.get("properties", {}), dict) else {}
    required = schema.get("required", []) if isinstance(schema.get("required", []), list) else []
    issues: list[dict[str, Any]] = []

    for field_name in required:
        if field_name not in params or params.get(field_name) is None or params.get(field_name) == "":
            issues.append({"path": [field_name], "message": "Required parameter is missing."})

    for field_name, value in params.items():
        expected = properties.get(field_name, {})
        if isinstance(expected, dict) and not _schema_type_matches(expected.get("type"), value):
            issues.append({
                "path": [field_name],
                "message": f"Expected {expected.get('type')}, received {type(value).__name__}.",
            })

    if not issues:
        return None
    return {
        "code": "ACTION_PARAMS_INVALID",
        "message": f"Invalid parameters for {action.id}.",
        "issues": issues,
    }


def _failure_event(base_event: dict[str, Any], status: str, message: str, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **base_event,
        "status": status,
        "message": message,
        "error": error,
    }


def execute_app_action(request: AppAutomationExecuteRequest) -> AppAutomationExecuteResult:
    action = get_action(request.action_id)
    if not action or action.app_id != request.app_id:
        error = {"code": "UNKNOWN_ACTION", "message": f"Unknown app action: {request.app_id}/{request.action_id}"}
        persisted_event = emit_app_automation_event(
            EventType.APP_AUTOMATION_VALIDATION_FAILED,
            request.session_id,
            app_id=request.app_id,
            action_id=request.action_id,
            status="unknown_action",
            message=error["message"],
            error=error,
            params_preview=redact_sensitive({key: str(value)[:120] for key, value in request.params.items()}),
        )
        return AppAutomationExecuteResult(
            ok=False,
            status="unknown_action",
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=request.dry_run,
            message=error["message"],
            event=persisted_event,
            error=error,
        )

    route_plan = build_action_plan(action)
    selected_vendor = route_plan.get("selected_vendor") or action.preferred_vendor
    selected_layer = route_plan.get("selected_layer") or action.execution_kind
    required_approval = action.approval == "required" and not request.approval_granted
    base_event = _make_base_event(action, request, route_plan, selected_vendor, selected_layer)
    planned_event = emit_app_automation_event(EventType.APP_AUTOMATION_PLANNED, request.session_id, **base_event)

    parameter_error = _validate_params(action, request.params)
    if parameter_error:
        validation_event = emit_app_automation_event(
            EventType.APP_AUTOMATION_VALIDATION_FAILED,
            request.session_id,
            **base_event,
            status="invalid_params",
            message=parameter_error["message"],
            error=parameter_error,
        )
        return AppAutomationExecuteResult(
            ok=False,
            status="invalid_params",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=request.dry_run,
            message=parameter_error["message"],
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=validation_event or planned_event,
            error=parameter_error,
        )

    if required_approval:
        blocked_event = emit_app_automation_event(
            EventType.APP_AUTOMATION_BLOCKED,
            request.session_id,
            **base_event,
            status="needs_approval",
            message=f"{action.label} requires approval before execution.",
            required_approval=True,
        )
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
            event=blocked_event or planned_event,
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
            event=planned_event or base_event,
        )

    if not _selected_candidate_installed(route_plan):
        error = {"code": "VENDOR_NOT_INSTALLED", "message": f"No installed vendor source is available for action {action.id}."}
        failed_event = emit_app_automation_event(
            EventType.APP_AUTOMATION_FAILED,
            request.session_id,
            **_failure_event(base_event, "vendor_not_installed", error["message"], error),
        )
        return AppAutomationExecuteResult(
            ok=False,
            status="vendor_not_installed",
            vendor=selected_vendor,
            execution_kind=action.execution_kind,
            app_id=request.app_id,
            action_id=request.action_id,
            dry_run=False,
            message=error["message"],
            planned_steps=_planned_steps(action, request, route_plan),
            route_plan=route_plan,
            event=failed_event or planned_event,
            error=error,
        )

    adapter = _adapter_for_vendor(selected_vendor)
    if adapter is None:
        error = {"code": "ADAPTER_MISSING", "message": "No adapter scaffold is registered."}
        failed_event = emit_app_automation_event(
            EventType.APP_AUTOMATION_FAILED,
            request.session_id,
            **_failure_event(base_event, "adapter_missing", "No platform adapter scaffold is registered for this vendor.", error),
        )
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
            event=failed_event or planned_event,
            error=error,
        )

    adapter_result = adapter.execute(action, request)
    event_type = EventType.APP_AUTOMATION_EXECUTED if adapter_result.ok else EventType.APP_AUTOMATION_FAILED
    runtime_event = emit_app_automation_event(
        event_type,
        request.session_id,
        **base_event,
        status=adapter_result.status,
        message=adapter_result.message,
        adapter_status=adapter_result.status,
        result=adapter_result.result,
        error=adapter_result.error,
    )
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
        result=adapter_result.result,
        event=runtime_event or planned_event or {**base_event, "adapter_status": adapter_result.status},
        error=adapter_result.error,
    )
