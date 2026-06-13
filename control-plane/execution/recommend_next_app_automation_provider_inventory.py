"""Top-level app-automation action inventory for recommend-next scaffolding.

Only provider-neutral action names are tracked by the recommend-next taxonomy.
Provider-specific or app-specific catalog IDs such as ``gmail.search_email`` or
``outlook.create_email`` are compatibility aliases, route evidence, or executor
inputs; they are not root-level tracked actions.

Definitions
-----------
``PROVIDER_ROUTE_SUPPORT`` records which provider routes can serve each
provider-neutral top-level action.

``APP_CATALOG_ACTION_ALIASES`` maps checked-in app-specific seed action IDs to
the top-level action names tracked by recommend-next.

``DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS`` is the provider-overlap-deduplicated
total action set known to the checked-in app-automation stack.
"""

from __future__ import annotations

from typing import Mapping

from execution.recommend_next_execution_service import RecommendNextDecisionType


PROVIDER_ROUTE_SUPPORT: Mapping[str, tuple[str, ...]] = {
    "activepieces": (
        "issue.create",
        "message.send",
        "email.search",
        "calendar_event.create",
        "spreadsheet_row.append",
        "page.create",
        "contact.create",
    ),
    "composio": (
        "issue.create",
        "repository.search",
        "message.send",
        "email.search",
        "calendar_event.create",
        "spreadsheet_row.append",
        "page.create",
        "contact.create",
    ),
    "mcp_servers": (
        "issue.create",
        "repository.search",
        "email.search",
    ),
    "n8n": (
        "message.send",
        "calendar_event.create",
        "spreadsheet_row.append",
        "page.create",
        "issue.create",
        "contact.create",
    ),
    "stagehand": (
        "browser_task.perform",
        "visual_browser_task.perform",
    ),
    "browser_use": (
        "browser_task.perform",
        "visual_browser_task.perform",
    ),
    "skyvern": (
        "browser_task.perform",
        "visual_browser_task.perform",
    ),
}


# Existing checked-in seed action IDs map to top-level action names. These IDs
# may still be used by the app-automation executor, but they are not root-level
# recommend-next action names.
APP_CATALOG_ACTION_ALIASES: Mapping[str, str] = {
    "github.create_issue": "issue.create",
    "linear.create_issue": "issue.create",
    "jira.create_issue": "issue.create",
    "github.search_repo": "repository.search",
    "gmail.search_email": "email.search",
    "slack.send_message": "message.send",
    "discord.send_message": "message.send",
    "google_calendar.create_event": "calendar_event.create",
    "google_sheets.append_row": "spreadsheet_row.append",
    "notion.create_page": "page.create",
    "hubspot.create_contact": "contact.create",
    "web.perform_task": "browser_task.perform",
    "web.visual_task": "visual_browser_task.perform",
}


LOCAL_ADAPTER_SUPPORT: Mapping[str, tuple[str, ...]] = {
    "activepieces": (
        "spreadsheet_row.append",
        "issue.create",
        "message.send",
    ),
    "composio": (
        "email.search",
        "message.send",
        "calendar_event.create",
        "page.create",
        "issue.create",
        "contact.create",
    ),
    "mcp_servers": (
        "repository.search",
        "issue.create",
    ),
    "n8n": (
        "message.send",
        "spreadsheet_row.append",
        "issue.create",
    ),
    "stagehand": (
        "browser_task.perform",
        "visual_browser_task.perform",
    ),
    "browser_use": (
        "browser_task.perform",
        "visual_browser_task.perform",
    ),
    "skyvern": (
        "visual_browser_task.perform",
        "browser_task.perform",
    ),
}


DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS: tuple[str, ...] = tuple(sorted({
    action_name
    for provider_actions in PROVIDER_ROUTE_SUPPORT.values()
    for action_name in provider_actions
} | {
    action_name
    for provider_actions in LOCAL_ADAPTER_SUPPORT.values()
    for action_name in provider_actions
}))


TOP_LEVEL_ACTION_PROVIDER_ROUTE_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    action_name: tuple(provider for provider, actions in PROVIDER_ROUTE_SUPPORT.items() if action_name in actions)
    for action_name in DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS
}


TOP_LEVEL_ACTION_LOCAL_ADAPTER_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    action_name: tuple(provider for provider, actions in LOCAL_ADAPTER_SUPPORT.items() if action_name in actions)
    for action_name in DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS
}


TOP_LEVEL_APP_AUTOMATION_ACTION_DECISION_TYPE: Mapping[str, RecommendNextDecisionType] = {
    "browser_task.perform": RecommendNextDecisionType.EXECUTE,
    "calendar_event.create": RecommendNextDecisionType.EXECUTE,
    "contact.create": RecommendNextDecisionType.EXECUTE,
    "email.search": RecommendNextDecisionType.FIND_OUT_MORE,
    "issue.create": RecommendNextDecisionType.EXECUTE,
    "message.send": RecommendNextDecisionType.EXECUTE,
    "page.create": RecommendNextDecisionType.EXECUTE,
    "repository.search": RecommendNextDecisionType.FIND_OUT_MORE,
    "spreadsheet_row.append": RecommendNextDecisionType.EXECUTE,
    "visual_browser_task.perform": RecommendNextDecisionType.EXECUTE,
}


# Scaffold invariant for future enforcement:
# sorted(TOP_LEVEL_APP_AUTOMATION_ACTION_DECISION_TYPE) must match
# DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS. App-specific IDs and provider names
# must remain aliases/route evidence and must not enter the root taxonomy.
