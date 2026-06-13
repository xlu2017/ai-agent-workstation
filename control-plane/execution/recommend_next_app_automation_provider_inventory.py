"""Provider-level app-automation action inventory for recommend-next scaffolding.

This file deduplicates the checked-in app-automation action surface across the
selected app-automation providers. It is scaffold-only: no runtime code imports
or enforces these maps yet.

Definitions
-----------
``PROVIDER_ROUTE_SUPPORT`` records the platform route matrix from
``api.app_automation.vendor_plan.ACTION_VENDOR_PREFERENCES``. This is the broad
provider coverage the control plane intends to route through.

``LOCAL_ADAPTER_SUPPORT`` records the narrower deterministic vendored adapter
contracts from ``vendor/app-automation/*/source/jubilant_goggles_adapter.py``.

``DEDUPED_APP_AUTOMATION_ACTION_IDS`` is the provider-overlap-deduplicated total
action set known to the checked-in app-automation stack.
"""

from __future__ import annotations

from typing import Mapping

from execution.recommend_next_execution_service import RecommendNextDecisionType


PROVIDER_ROUTE_SUPPORT: Mapping[str, tuple[str, ...]] = {
    "activepieces": (
        "github.create_issue",
        "slack.send_message",
        "gmail.search_email",
        "google_calendar.create_event",
        "google_sheets.append_row",
        "notion.create_page",
        "linear.create_issue",
        "jira.create_issue",
        "discord.send_message",
        "hubspot.create_contact",
    ),
    "composio": (
        "github.create_issue",
        "github.search_repo",
        "slack.send_message",
        "gmail.search_email",
        "google_calendar.create_event",
        "google_sheets.append_row",
        "notion.create_page",
        "linear.create_issue",
        "jira.create_issue",
        "discord.send_message",
        "hubspot.create_contact",
    ),
    "mcp_servers": (
        "github.create_issue",
        "github.search_repo",
        "gmail.search_email",
    ),
    "n8n": (
        "slack.send_message",
        "google_calendar.create_event",
        "google_sheets.append_row",
        "notion.create_page",
        "jira.create_issue",
        "discord.send_message",
        "hubspot.create_contact",
    ),
    "stagehand": (
        "web.perform_task",
        "web.visual_task",
    ),
    "browser_use": (
        "web.perform_task",
        "web.visual_task",
    ),
    "skyvern": (
        "web.perform_task",
        "web.visual_task",
    ),
}


LOCAL_ADAPTER_SUPPORT: Mapping[str, tuple[str, ...]] = {
    "activepieces": (
        "google_sheets.append_row",
        "jira.create_issue",
        "discord.send_message",
        "slack.send_message",
    ),
    "composio": (
        "gmail.search_email",
        "slack.send_message",
        "google_calendar.create_event",
        "notion.create_page",
        "linear.create_issue",
        "hubspot.create_contact",
    ),
    "mcp_servers": (
        "github.search_repo",
        "github.create_issue",
    ),
    "n8n": (
        "slack.send_message",
        "google_sheets.append_row",
        "jira.create_issue",
        "discord.send_message",
    ),
    "stagehand": (
        "web.perform_task",
        "web.visual_task",
    ),
    "browser_use": (
        "web.perform_task",
        "web.visual_task",
    ),
    "skyvern": (
        "web.visual_task",
        "web.perform_task",
    ),
}


DEDUPED_APP_AUTOMATION_ACTION_IDS: tuple[str, ...] = tuple(sorted({
    action_id
    for provider_actions in PROVIDER_ROUTE_SUPPORT.values()
    for action_id in provider_actions
} | {
    action_id
    for provider_actions in LOCAL_ADAPTER_SUPPORT.values()
    for action_id in provider_actions
}))


ACTION_PROVIDER_ROUTE_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    action_id: tuple(provider for provider, actions in PROVIDER_ROUTE_SUPPORT.items() if action_id in actions)
    for action_id in DEDUPED_APP_AUTOMATION_ACTION_IDS
}


ACTION_LOCAL_ADAPTER_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    action_id: tuple(provider for provider, actions in LOCAL_ADAPTER_SUPPORT.items() if action_id in actions)
    for action_id in DEDUPED_APP_AUTOMATION_ACTION_IDS
}


APP_AUTOMATION_ACTION_DECISION_TYPE: Mapping[str, RecommendNextDecisionType] = {
    "github.create_issue": RecommendNextDecisionType.EXECUTE,
    "github.search_repo": RecommendNextDecisionType.FIND_OUT_MORE,
    "slack.send_message": RecommendNextDecisionType.EXECUTE,
    "gmail.search_email": RecommendNextDecisionType.FIND_OUT_MORE,
    "google_calendar.create_event": RecommendNextDecisionType.EXECUTE,
    "google_sheets.append_row": RecommendNextDecisionType.EXECUTE,
    "notion.create_page": RecommendNextDecisionType.EXECUTE,
    "linear.create_issue": RecommendNextDecisionType.EXECUTE,
    "jira.create_issue": RecommendNextDecisionType.EXECUTE,
    "discord.send_message": RecommendNextDecisionType.EXECUTE,
    "hubspot.create_contact": RecommendNextDecisionType.EXECUTE,
    "web.perform_task": RecommendNextDecisionType.EXECUTE,
    "web.visual_task": RecommendNextDecisionType.EXECUTE,
}


# Scaffold invariant for future enforcement:
# sorted(APP_AUTOMATION_ACTION_DECISION_TYPE) must match
# DEDUPED_APP_AUTOMATION_ACTION_IDS, so every deduplicated app action is under
# exactly one of execute, find_out_more, ask_user, or stop.
