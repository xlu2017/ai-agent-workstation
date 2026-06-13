"""App-automation action taxonomy for the recommend-next boundary.

This scaffold classifies app-automation actions under the four controller-level
recommend-next categories. It is documentation-only code: no runtime imports or
request paths currently depend on it.

The source action surfaces are:

* api/routes/app_automation.py endpoint operations
* api/app_automation/registry.py seed AppAction IDs
* api/app_automation/executor.py validation, dry-run, approval, and dispatch paths
* api/app_automation/runtime.py vendor runtime paths
* vendor/app-automation/*/source/jubilant_goggles_adapter.py supported actions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from execution.recommend_next_execution_service import RecommendNextDecisionType


@dataclass(frozen=True)
class AppAutomationCategoryEntry:
    action_name: str
    decision_type: RecommendNextDecisionType
    source_surface: str
    rationale: str


APP_AUTOMATION_EXECUTE_ACTIONS: tuple[AppAutomationCategoryEntry, ...] = (
    # Route-level operations that mutate app-automation configuration or begin execution.
    AppAutomationCategoryEntry("app_automation.save_vendor_config", RecommendNextDecisionType.EXECUTE, "route/config", "Persist runtime configuration for a vendor."),
    AppAutomationCategoryEntry("app_automation.clear_vendor_config", RecommendNextDecisionType.EXECUTE, "route/config", "Clear stored runtime configuration for a vendor."),
    AppAutomationCategoryEntry("app_automation.execute", RecommendNextDecisionType.EXECUTE, "route", "Enter the app-automation executor endpoint."),
    AppAutomationCategoryEntry("app_automation.execute_action", RecommendNextDecisionType.EXECUTE, "executor", "Execute a selected app action after validation and gates."),
    AppAutomationCategoryEntry("app_automation.dispatch_vendor_runtime", RecommendNextDecisionType.EXECUTE, "runtime", "Dispatch a normalized action envelope to a selected vendor."),
    AppAutomationCategoryEntry("app_automation.execute_configured_http_endpoint", RecommendNextDecisionType.EXECUTE, "runtime", "Dispatch a normalized action envelope to a configured vendor HTTP endpoint."),
    AppAutomationCategoryEntry("app_automation.execute_configured_command", RecommendNextDecisionType.EXECUTE, "runtime", "Dispatch a normalized action envelope to a configured vendor command."),
    AppAutomationCategoryEntry("app_automation.execute_local_vendor_adapter", RecommendNextDecisionType.EXECUTE, "runtime", "Run a vendored local adapter contract."),
    AppAutomationCategoryEntry("app_automation.mock_execute", RecommendNextDecisionType.EXECUTE, "runtime", "Run the deterministic mock execution path."),
    AppAutomationCategoryEntry("app_automation.emit_planned_event", RecommendNextDecisionType.EXECUTE, "event_log", "Persist a planned audit event."),
    AppAutomationCategoryEntry("app_automation.emit_blocked_event", RecommendNextDecisionType.EXECUTE, "event_log", "Persist a blocked audit event."),
    AppAutomationCategoryEntry("app_automation.emit_executed_event", RecommendNextDecisionType.EXECUTE, "event_log", "Persist an executed audit event."),
    AppAutomationCategoryEntry("app_automation.emit_failed_event", RecommendNextDecisionType.EXECUTE, "event_log", "Persist a failed audit event."),
    AppAutomationCategoryEntry("app_automation.emit_validation_failed_event", RecommendNextDecisionType.EXECUTE, "event_log", "Persist a validation-failed audit event."),
    # Seed AppAction IDs with modification or side-effect risk.
    AppAutomationCategoryEntry("github.create_issue", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a GitHub issue."),
    AppAutomationCategoryEntry("slack.send_message", RecommendNextDecisionType.EXECUTE, "seed_action", "Send a Slack message."),
    AppAutomationCategoryEntry("google_calendar.create_event", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a calendar event."),
    AppAutomationCategoryEntry("google_sheets.append_row", RecommendNextDecisionType.EXECUTE, "seed_action", "Append a row to a sheet."),
    AppAutomationCategoryEntry("notion.create_page", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a Notion page."),
    AppAutomationCategoryEntry("linear.create_issue", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a Linear issue."),
    AppAutomationCategoryEntry("jira.create_issue", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a Jira issue."),
    AppAutomationCategoryEntry("discord.send_message", RecommendNextDecisionType.EXECUTE, "seed_action", "Send a Discord message."),
    AppAutomationCategoryEntry("hubspot.create_contact", RecommendNextDecisionType.EXECUTE, "seed_action", "Create a HubSpot contact."),
    AppAutomationCategoryEntry("web.perform_task", RecommendNextDecisionType.EXECUTE, "seed_action", "Perform a browser app task."),
    AppAutomationCategoryEntry("web.visual_task", RecommendNextDecisionType.EXECUTE, "seed_action", "Perform a visual browser app task."),
)


APP_AUTOMATION_FIND_OUT_MORE_ACTIONS: tuple[AppAutomationCategoryEntry, ...] = (
    AppAutomationCategoryEntry("app_automation.list_vendors", RecommendNextDecisionType.FIND_OUT_MORE, "route", "Read vendor catalog and status."),
    AppAutomationCategoryEntry("app_automation.list_config", RecommendNextDecisionType.FIND_OUT_MORE, "route/config", "Read redacted runtime configuration status."),
    AppAutomationCategoryEntry("app_automation.get_vendor_config", RecommendNextDecisionType.FIND_OUT_MORE, "route/config", "Read redacted status for one vendor."),
    AppAutomationCategoryEntry("app_automation.list_capabilities", RecommendNextDecisionType.FIND_OUT_MORE, "route", "Read vendor capability matrix."),
    AppAutomationCategoryEntry("app_automation.list_actions", RecommendNextDecisionType.FIND_OUT_MORE, "route", "Read normalized app actions."),
    AppAutomationCategoryEntry("app_automation.get_action_plan", RecommendNextDecisionType.FIND_OUT_MORE, "route", "Read a vendor route plan for one action."),
    AppAutomationCategoryEntry("app_automation.list_events", RecommendNextDecisionType.FIND_OUT_MORE, "route/event_log", "Read app-automation audit events."),
    AppAutomationCategoryEntry("app_automation.validate_params", RecommendNextDecisionType.FIND_OUT_MORE, "executor", "Validate app-action parameters."),
    AppAutomationCategoryEntry("app_automation.build_action_plan", RecommendNextDecisionType.FIND_OUT_MORE, "vendor_plan", "Build a read-only route plan."),
    AppAutomationCategoryEntry("app_automation.route_candidates_for_action", RecommendNextDecisionType.FIND_OUT_MORE, "vendor_plan", "Inspect vendor candidates for one action."),
    AppAutomationCategoryEntry("app_automation.vendor_status", RecommendNextDecisionType.FIND_OUT_MORE, "registry", "Inspect vendor source and adapter presence."),
    AppAutomationCategoryEntry("app_automation.adapter_health", RecommendNextDecisionType.FIND_OUT_MORE, "adapter", "Inspect adapter health."),
    AppAutomationCategoryEntry("app_automation.dry_run_action", RecommendNextDecisionType.FIND_OUT_MORE, "executor", "Return a dry-run plan without live vendor execution."),
    AppAutomationCategoryEntry("github.search_repo", RecommendNextDecisionType.FIND_OUT_MORE, "seed_action", "Search GitHub content or issues."),
    AppAutomationCategoryEntry("gmail.search_email", RecommendNextDecisionType.FIND_OUT_MORE, "seed_action", "Search Gmail messages."),
)


APP_AUTOMATION_ASK_USER_ACTIONS: tuple[AppAutomationCategoryEntry, ...] = (
    AppAutomationCategoryEntry("app_automation.ask_for_approval", RecommendNextDecisionType.ASK_USER, "executor", "Ask the user to approve a gated action."),
    AppAutomationCategoryEntry("app_automation.ask_for_missing_params", RecommendNextDecisionType.ASK_USER, "executor", "Ask the user for missing action parameters."),
    AppAutomationCategoryEntry("app_automation.ask_for_vendor_config", RecommendNextDecisionType.ASK_USER, "config/runtime", "Ask the user or operator to configure a needed vendor runtime."),
)


APP_AUTOMATION_STOP_ACTIONS: tuple[AppAutomationCategoryEntry, ...] = (
    AppAutomationCategoryEntry("app_automation.unknown_action", RecommendNextDecisionType.STOP, "executor", "Unknown app action; fail closed."),
    AppAutomationCategoryEntry("app_automation.invalid_params", RecommendNextDecisionType.STOP, "executor", "Invalid parameters; do not execute."),
    AppAutomationCategoryEntry("app_automation.needs_approval", RecommendNextDecisionType.STOP, "executor", "Stop until approval is granted."),
    AppAutomationCategoryEntry("app_automation.vendor_not_installed", RecommendNextDecisionType.STOP, "executor/runtime", "Selected vendor source is unavailable."),
    AppAutomationCategoryEntry("app_automation.adapter_missing", RecommendNextDecisionType.STOP, "executor/runtime", "Selected vendor adapter is missing."),
    AppAutomationCategoryEntry("app_automation.adapter_not_supported", RecommendNextDecisionType.STOP, "runtime", "No runtime adapter supports the selected vendor."),
    AppAutomationCategoryEntry("app_automation.runtime_not_configured", RecommendNextDecisionType.STOP, "runtime", "Live runtime is not configured."),
    AppAutomationCategoryEntry("app_automation.runtime_error", RecommendNextDecisionType.STOP, "runtime", "Runtime failed; stop until inspected or retried."),
    AppAutomationCategoryEntry("app_automation.action_not_supported_by_local_adapter", RecommendNextDecisionType.STOP, "vendor_adapter", "Vendored local adapter rejected the action."),
)


ALL_APP_AUTOMATION_CATEGORY_ENTRIES: tuple[AppAutomationCategoryEntry, ...] = (
    *APP_AUTOMATION_EXECUTE_ACTIONS,
    *APP_AUTOMATION_FIND_OUT_MORE_ACTIONS,
    *APP_AUTOMATION_ASK_USER_ACTIONS,
    *APP_AUTOMATION_STOP_ACTIONS,
)


APP_AUTOMATION_DECISION_TYPE_BY_ACTION: Mapping[str, RecommendNextDecisionType] = {
    entry.action_name: entry.decision_type for entry in ALL_APP_AUTOMATION_CATEGORY_ENTRIES
}


APP_AUTOMATION_RISK_DECISION_TYPE_BY_RISK: Mapping[str, RecommendNextDecisionType] = {
    "read_only": RecommendNextDecisionType.FIND_OUT_MORE,
    "modification": RecommendNextDecisionType.EXECUTE,
    "external_side_effect": RecommendNextDecisionType.EXECUTE,
}


# Scaffold invariant for future implementation:
# Any new app-automation action ID, route operation, vendor dispatch operation,
# or adapter status that recommend-next may output must be added here before it
# can pass validation. Do not silently default unknown app-automation names to
# execute.
