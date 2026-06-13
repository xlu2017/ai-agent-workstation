"""Provider-neutral app automation action resolver.

Recommend-next emits top-level action names such as ``email.create`` and carries
app/provider specificity in params. The app-automation executor should dispatch
that provider-neutral action directly to the selected vendor runtime/adapter.
Provider-specific legacy IDs are accepted only as aliases and normalized before
execution.
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
    """Resolved provider-neutral app action for direct vendor dispatch."""

    top_level_action_name: str
    app_id: str
    action_id: str
    params: dict[str, Any]
    source_action_name: str


def is_provider_neutral_app_action(action_name: str) -> bool:
    return action_name in PROVIDER_NEUTRAL_ACTION_NAMES or action_name in APP_CATALOG_ACTION_ALIASES


def resolve_provider_neutral_app_action(action_name: str, params: dict[str, Any] | None = None) -> ProviderNeutralAppActionResolution:
    """Normalize aliases while preserving provider-specific choices as params."""

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
    raw_params.setdefault("source_action_name", action_name)

    # Legacy catalog IDs may be useful for audit/debugging, but do not become the
    # executor action_id. The executor action_id remains provider-neutral so the
    # selected vendor adapter receives the top-level function directly.
    if action_name in APP_CATALOG_ACTION_ALIASES:
        raw_params.setdefault("catalog_action_id", action_name)

    return ProviderNeutralAppActionResolution(
        top_level_action_name=top_level,
        app_id=top_level.split(".", 1)[0],
        action_id=top_level,
        params=raw_params,
        source_action_name=action_name,
    )
