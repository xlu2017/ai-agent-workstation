"""Top-level provider-neutral seed actions for app automation.

Recommend-next emits these action IDs directly. Provider-specific services such
as Gmail, Outlook, Slack, GitHub, and Jira are carried in params and consumed by
the selected vendor adapter/runtime.
"""

from __future__ import annotations

from typing import Any

from api.app_automation.models import AppAction


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": True}


PROVIDER_NEUTRAL_SEED_ACTIONS: list[AppAction] = [
    AppAction(
        id="browser_task.perform",
        app_id="browser_task",
        label="Perform browser task",
        description="Perform a browser automation task through a provider selected by params.browser_provider or params.automation_vendor.",
        execution_kind="browser",
        preferred_vendor="stagehand",
        risk="modification",
        approval="preview",
        input_schema=_schema({"instruction": {"type": "string"}, "url": {"type": "string"}, "browser_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["instruction"]),
    ),
    AppAction(
        id="calendar_event.create",
        app_id="calendar_event",
        label="Create calendar event",
        description="Create a calendar event through a provider selected by params.calendar_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "attendees": {"type": "array"}, "calendar_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["title", "start", "end"]),
    ),
    AppAction(
        id="contact.create",
        app_id="contact",
        label="Create contact",
        description="Create a contact through a provider selected by params.contact_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"email": {"type": "string"}, "firstname": {"type": "string"}, "lastname": {"type": "string"}, "contact_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["email"]),
    ),
    AppAction(
        id="email.create",
        app_id="email",
        label="Create email draft",
        description="Create an email draft through a provider selected by params.email_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="modification",
        approval="preview",
        input_schema=_schema({"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "cc": {"type": "array"}, "bcc": {"type": "array"}, "email_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["to"]),
    ),
    AppAction(
        id="email.search",
        app_id="email",
        label="Search email",
        description="Search email through a provider selected by params.email_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="read_only",
        approval="none",
        input_schema=_schema({"query": {"type": "string"}, "limit": {"type": "integer"}, "email_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["query"]),
    ),
    AppAction(
        id="email.send",
        app_id="email",
        label="Send email",
        description="Send an email through a provider selected by params.email_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "cc": {"type": "array"}, "bcc": {"type": "array"}, "email_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["to", "body"]),
    ),
    AppAction(
        id="issue.create",
        app_id="issue",
        label="Create issue",
        description="Create an issue or ticket through a provider selected by params.issue_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"title": {"type": "string"}, "body": {"type": "string"}, "description": {"type": "string"}, "repo": {"type": "string"}, "team": {"type": "string"}, "project": {"type": "string"}, "issue_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["title"]),
    ),
    AppAction(
        id="message.send",
        app_id="message",
        label="Send message",
        description="Send a message through a provider selected by params.message_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"text": {"type": "string"}, "channel": {"type": "string"}, "recipient": {"type": "string"}, "message_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["text"]),
    ),
    AppAction(
        id="page.create",
        app_id="page",
        label="Create page",
        description="Create a page through a provider selected by params.page_provider.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="modification",
        approval="preview",
        input_schema=_schema({"title": {"type": "string"}, "parent": {"type": "string"}, "content": {"type": "string"}, "page_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["title"]),
    ),
    AppAction(
        id="repository.search",
        app_id="repository",
        label="Search repository",
        description="Search repository content, issues, or pull requests through a provider selected by params.repository_provider.",
        execution_kind="mcp",
        preferred_vendor="mcp_servers",
        risk="read_only",
        approval="none",
        input_schema=_schema({"repo": {"type": "string"}, "query": {"type": "string"}, "kind": {"type": "string"}, "repository_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["repo", "query"]),
    ),
    AppAction(
        id="spreadsheet_row.append",
        app_id="spreadsheet_row",
        label="Append spreadsheet row",
        description="Append a row to a spreadsheet through a provider selected by params.spreadsheet_provider.",
        execution_kind="workflow",
        preferred_vendor="activepieces",
        risk="modification",
        approval="preview",
        input_schema=_schema({"spreadsheet_id": {"type": "string"}, "sheet": {"type": "string"}, "row": {"type": "array"}, "spreadsheet_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["spreadsheet_id", "row"]),
    ),
    AppAction(
        id="visual_browser_task.perform",
        app_id="visual_browser_task",
        label="Perform visual browser task",
        description="Perform a visual browser automation task through a provider selected by params.browser_provider or params.automation_vendor.",
        execution_kind="visual_browser",
        preferred_vendor="skyvern",
        risk="modification",
        approval="preview",
        input_schema=_schema({"instruction": {"type": "string"}, "url": {"type": "string"}, "browser_provider": {"type": "string"}, "automation_vendor": {"type": "string"}}, ["instruction"]),
    ),
]
