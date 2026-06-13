"""Provider-neutral app automation action resolver.

This is the bridge between recommend-next root action names and the existing
app-automation catalog/action executor. Recommend-next should output top-level
action names such as ``email.create`` and provider specificity in params; the
app-automation executor still consumes app-specific catalog IDs such as
``gmail.create_email``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROVIDER_PARAMETER_BY_ACTION: dict[str, str] = {
    "browser_task.perform": "browser_provider",
    "calendar_event.create": "calendar_provider",
    "contact.create": "contact_provider",
    "email.create": "email_provider",
    "email.search": "email_provider",
    "email.send": "email_provider",
    "issue.create": "issue_provider",
    "message.send": "message_provider",
    "page.create": "page_provider",
    "repository.search": "repository_provider",
    "spreadsheet_row.append": "spreadsheet_provider",
    "visual_browser_task.perform": "browser_provider",
}

APP_CATALOG_ACTION_ALIASES: dict[str, str] = {
    "discord.send_message": "message.send",
    "github.create_issue": "issue.create",
    "github.search_repo": "repository.search",
    "gmail.create_email": "email.create",
    "gmail.search_email": "email.search",
    "gmail.send_email": "email.send",
    "google_calendar.create_event": "calendar_event.create",
    "google_sheets.append_row": "spreadsheet_row.append",
    "hubspot.create_contact": "contact.create",
    "jira.create_issue": "issue.create",
    "linear.create_issue": "issue.create",
    "notion.create_page": "page.create",
    "outlook.create_email": "email.create",
    "outlook.send_email": "email.send",
    "outlook_calendar.create_event": "calendar_event.create",
    "slack.send_message": "message.send",
    "web.perform_task": "browser_task.perform",
    "web.visual_task": "visual_browser_task.perform",
}

CATALOG_ACTION_BY_TOP_LEVEL_AND_PROVIDER: dict[tuple[str, str], str] = {
    ("browser_task.perform", "web"): "web.perform_task",
    ("browser_task.perform", "stagehand"): "web.perform_task",
    ("browser_task.perform", "browser_use"): "web.perform_task",
    ("browser_task.perform", "skyvern"): "web.perform_task",
    ("calendar_event.create", "google_calendar"): "google_calendar.create_event",
    ("calendar_event.create", "outlook_calendar"): "outlook_calendar.create_event",
    ("contact.create", "hubspot"): "hubspot.create_contact",
    ("email.create", "gmail"): "gmail.create_email",
    ("email.create", "outlook"): "outlook.create_email",
    ("email.search", "gmail"): "gmail.search_email",
    ("email.send", "gmail"): "gmail.send_email",
    ("email.send", "outlook"): "outlook.send_email",
    ("issue.create", "github"): "github.create_issue",
    ("issue.create", "jira"): "jira.create_issue",
    ("issue.create", "linear"): "linear.create_issue",
    ("message.send", "discord"): "discord.send_message",
    ("message.send", "slack"): "slack.send_message",
    ("page.create", "notion"): "notion.create_page",
    ("repository.search", "github"): "github.search_repo",
    ("spreadsheet_row.append", "google_sheets"): "google_sheets.append_row",
    ("visual_browser_task.perform", "web"): "web.visual_task",
    ("visual_browser_task.perform", "stagehand"): "web.visual_task",
    ("visual_browser_task.perform", "browser_use"): "web.visual_task",
    ("visual_browser_task.perform", "skyvern"): "web.visual_task",
}

DEFAULT_PROVIDER_BY_TOP_LEVEL_ACTION: dict[str, str] = {
    "browser_task.perform": "stagehand",
    "calendar_event.create": "google_calendar",
    "contact.create": "hubspot",
    "email.create": "gmail",
    "email.search": "gmail",
    "email.send": "gmail",
    "issue.create": "github",
    "message.send": "slack",
    "page.create": "notion",
    "repository.search": "github",
    "spreadsheet_row.append": "google_sheets",
    "visual_browser_task.perform": "skyvern",
}

PROVIDER_NEUTRAL_ACTION_NAMES = frozenset(PROVIDER_PARAMETER_BY_ACTION)


@dataclass(frozen=True)
class ProviderNeutralAppActionResolution:
    """Resolved app-automation action for the existing executor contract."""

    top_level_action_name: str
    app_id: str
    action_id: str
    params: dict[str, Any]
    source_action_name: str


def is_provider_neutral_app_action(action_name: str) -> bool:
    return action_name in PROVIDER_NEUTRAL_ACTION_NAMES or action_name in APP_CATALOG_ACTION_ALIASES


def resolve_provider_neutral_app_action(action_name: str, params: dict[str, Any] | None = None) -> ProviderNeutralAppActionResolution:
    """Resolve a root or alias action name to an app-automation catalog action."""

    raw_params = dict(params or {})
    top_level = APP_CATALOG_ACTION_ALIASES.get(action_name, action_name)
    if top_level not in PROVIDER_NEUTRAL_ACTION_NAMES:
        raise ValueError(f"Unknown provider-neutral app action: {action_name}")

    provider_param = PROVIDER_PARAMETER_BY_ACTION[top_level]
    provider = str(raw_params.get(provider_param) or "").strip()
    if not provider and action_name in APP_CATALOG_ACTION_ALIASES:
        provider = action_name.split(".", 1)[0]
    if not provider:
        provider = DEFAULT_PROVIDER_BY_TOP_LEVEL_ACTION[top_level]
    raw_params.setdefault(provider_param, provider)

    catalog_action_id = str(raw_params.get("catalog_action_id") or "").strip()
    if not catalog_action_id:
        catalog_action_id = CATALOG_ACTION_BY_TOP_LEVEL_AND_PROVIDER.get((top_level, provider), "")
    if not catalog_action_id:
        raise ValueError(f"No app-automation catalog action for {top_level} with {provider_param}={provider}")
    raw_params.setdefault("catalog_action_id", catalog_action_id)

    app_id = catalog_action_id.split(".", 1)[0]
    executor_params = _adapt_params_for_catalog_action(catalog_action_id, raw_params)
    return ProviderNeutralAppActionResolution(
        top_level_action_name=top_level,
        app_id=app_id,
        action_id=catalog_action_id,
        params=executor_params,
        source_action_name=action_name,
    )


def _adapt_params_for_catalog_action(action_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Translate provider-neutral parameter names to catalog-specific keys."""

    adapted = dict(params)
    if action_id == "jira.create_issue" and "summary" not in adapted and "title" in adapted:
        adapted["summary"] = adapted["title"]
    if action_id == "linear.create_issue" and "description" not in adapted and "body" in adapted:
        adapted["description"] = adapted["body"]
    if action_id == "google_calendar.create_event" and "title" not in adapted and "summary" in adapted:
        adapted["title"] = adapted["summary"]
    return adapted
