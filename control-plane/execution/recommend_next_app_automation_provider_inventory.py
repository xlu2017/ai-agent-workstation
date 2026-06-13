"""Top-level app-automation action inventory for recommend-next scaffolding.

Only provider-neutral action names are tracked by the recommend-next taxonomy.
Provider-specific or app-specific catalog IDs such as ``gmail.search_email`` or
``outlook.create_email`` are compatibility aliases, route evidence, or executor
inputs; they are not root-level tracked actions.

Definitions
-----------
``PROVIDER_ROUTE_SUPPORT`` records which automation runtime providers can serve
each provider-neutral top-level action.

``APP_CATALOG_ACTION_ALIASES`` maps checked-in app-specific seed action IDs to
the top-level action names tracked by recommend-next.

``TOP_LEVEL_ACTION_PARAMETER_SCHEMAS`` records how app-specific provider choices
are carried as parameters. For example, ``email.create`` remains the action while
``email_provider=outlook`` or ``email_provider=gmail`` is parameter data.

``DEDUPED_TOP_LEVEL_APP_AUTOMATION_ACTIONS`` is the provider-overlap-deduplicated
total action set known to the checked-in app-automation stack plus scaffolded
provider-neutral email actions needed for the future provider-parameter model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from execution.recommend_next_execution_service import RecommendNextDecisionType


@dataclass(frozen=True)
class TopLevelActionParameterSchema:
    """Provider-neutral action parameter schema scaffold.

    ``provider_parameter`` identifies the parameter that stores the app-specific
    provider, service, or product family. ``automation_vendor_parameter`` stores
    the execution vendor route when a caller needs to constrain it; this remains
    metadata and must not become part of the root action name.
    """

    action_name: str
    provider_parameter: str | None = None
    automation_vendor_parameter: str = "automation_vendor"
    catalog_action_id_parameter: str = "catalog_action_id"
    required_parameters: tuple[str, ...] = ()
    optional_parameters: tuple[str, ...] = ()
    provider_examples: tuple[str, ...] = ()
    notes: str = ""


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
        "email.create",
        "email.send",
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
        "email.send",
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
    "gmail.create_email": "email.create",
    "gmail.send_email": "email.send",
    "outlook.create_email": "email.create",
    "outlook.send_email": "email.send",
    "slack.send_message": "message.send",
    "discord.send_message": "message.send",
    "google_calendar.create_event": "calendar_event.create",
    "outlook_calendar.create_event": "calendar_event.create",
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


TOP_LEVEL_ACTION_PARAMETER_SCHEMAS: Mapping[str, TopLevelActionParameterSchema] = {
    "browser_task.perform": TopLevelActionParameterSchema(
        action_name="browser_task.perform",
        provider_parameter="browser_provider",
        required_parameters=("instruction",),
        optional_parameters=("url", "browser_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("web", "stagehand", "browser_use"),
        notes="Use provider parameters for web target/runtime hints; do not encode provider in the action name.",
    ),
    "calendar_event.create": TopLevelActionParameterSchema(
        action_name="calendar_event.create",
        provider_parameter="calendar_provider",
        required_parameters=("title", "start", "end"),
        optional_parameters=("attendees", "calendar_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("google_calendar", "outlook_calendar"),
    ),
    "contact.create": TopLevelActionParameterSchema(
        action_name="contact.create",
        provider_parameter="contact_provider",
        required_parameters=("email",),
        optional_parameters=("firstname", "lastname", "contact_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("hubspot", "salesforce"),
    ),
    "email.create": TopLevelActionParameterSchema(
        action_name="email.create",
        provider_parameter="email_provider",
        required_parameters=("to",),
        optional_parameters=("subject", "body", "cc", "bcc", "email_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("gmail", "outlook"),
        notes="Create or draft an email; provider-specific services are parameters.",
    ),
    "email.search": TopLevelActionParameterSchema(
        action_name="email.search",
        provider_parameter="email_provider",
        required_parameters=("query",),
        optional_parameters=("limit", "email_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("gmail", "outlook"),
    ),
    "email.send": TopLevelActionParameterSchema(
        action_name="email.send",
        provider_parameter="email_provider",
        required_parameters=("to", "body"),
        optional_parameters=("subject", "cc", "bcc", "email_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("gmail", "outlook"),
    ),
    "issue.create": TopLevelActionParameterSchema(
        action_name="issue.create",
        provider_parameter="issue_provider",
        required_parameters=("title",),
        optional_parameters=("repo", "team", "project", "body", "description", "issue_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("github", "linear", "jira"),
    ),
    "message.send": TopLevelActionParameterSchema(
        action_name="message.send",
        provider_parameter="message_provider",
        required_parameters=("text",),
        optional_parameters=("channel", "recipient", "message_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("slack", "discord", "teams"),
    ),
    "page.create": TopLevelActionParameterSchema(
        action_name="page.create",
        provider_parameter="page_provider",
        required_parameters=("title",),
        optional_parameters=("parent", "content", "page_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("notion", "confluence"),
    ),
    "repository.search": TopLevelActionParameterSchema(
        action_name="repository.search",
        provider_parameter="repository_provider",
        required_parameters=("repo", "query"),
        optional_parameters=("kind", "repository_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("github", "gitlab"),
    ),
    "spreadsheet_row.append": TopLevelActionParameterSchema(
        action_name="spreadsheet_row.append",
        provider_parameter="spreadsheet_provider",
        required_parameters=("spreadsheet_id", "row"),
        optional_parameters=("sheet", "spreadsheet_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("google_sheets", "excel"),
    ),
    "visual_browser_task.perform": TopLevelActionParameterSchema(
        action_name="visual_browser_task.perform",
        provider_parameter="browser_provider",
        required_parameters=("instruction",),
        optional_parameters=("url", "browser_provider", "automation_vendor", "catalog_action_id"),
        provider_examples=("web", "skyvern"),
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
} | set(TOP_LEVEL_ACTION_PARAMETER_SCHEMAS.keys())))


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
    "email.create": RecommendNextDecisionType.EXECUTE,
    "email.search": RecommendNextDecisionType.FIND_OUT_MORE,
    "email.send": RecommendNextDecisionType.EXECUTE,
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
