"""Additional seed actions for provider-neutral app-action routing.

These actions let the provider-neutral recommend-next actions ``email.create``
and ``email.send`` resolve to concrete app-automation catalog IDs while keeping
the root action name provider-neutral.
"""

from __future__ import annotations

from typing import Any

from api.app_automation.models import AppAction


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": True}


PROVIDER_NEUTRAL_SEED_ACTIONS: list[AppAction] = [
    AppAction(
        id="gmail.create_email",
        app_id="gmail",
        label="Create Gmail draft",
        description="Create a Gmail draft without sending it.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="modification",
        approval="preview",
        input_schema=_schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "email_provider": {"type": "string"},
                "catalog_action_id": {"type": "string"},
                "automation_vendor": {"type": "string"},
            },
            ["to"],
        ),
    ),
    AppAction(
        id="gmail.send_email",
        app_id="gmail",
        label="Send Gmail email",
        description="Send an email through Gmail.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "email_provider": {"type": "string"},
                "catalog_action_id": {"type": "string"},
                "automation_vendor": {"type": "string"},
            },
            ["to", "body"],
        ),
    ),
    AppAction(
        id="outlook.create_email",
        app_id="outlook",
        label="Create Outlook draft",
        description="Create an Outlook email draft without sending it.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="modification",
        approval="preview",
        input_schema=_schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "email_provider": {"type": "string"},
                "catalog_action_id": {"type": "string"},
                "automation_vendor": {"type": "string"},
            },
            ["to"],
        ),
    ),
    AppAction(
        id="outlook.send_email",
        app_id="outlook",
        label="Send Outlook email",
        description="Send an email through Outlook.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "email_provider": {"type": "string"},
                "catalog_action_id": {"type": "string"},
                "automation_vendor": {"type": "string"},
            },
            ["to", "body"],
        ),
    ),
    AppAction(
        id="outlook_calendar.create_event",
        app_id="outlook_calendar",
        label="Create Outlook calendar event",
        description="Create an Outlook Calendar event.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema(
            {
                "title": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "attendees": {"type": "array"},
                "calendar_provider": {"type": "string"},
                "catalog_action_id": {"type": "string"},
                "automation_vendor": {"type": "string"},
            },
            ["title", "start", "end"],
        ),
    ),
]
