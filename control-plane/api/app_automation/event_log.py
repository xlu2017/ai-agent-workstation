"""Audit event helpers for app automation execution.

App automation runs may touch third-party systems, so the executor records a
small, redacted event stream into the session event log. These helpers keep
catalog validation, approval blocks, runtime failures, and successful execution
observable without leaking credentials or large vendor payloads.
"""

from __future__ import annotations

import os
from typing import Any

from live_feed.events import EventStore, EventType, create_event

APP_AUTOMATION_EVENT_TYPES = {
    EventType.APP_AUTOMATION_PLANNED.value,
    EventType.APP_AUTOMATION_VALIDATION_FAILED.value,
    EventType.APP_AUTOMATION_BLOCKED.value,
    EventType.APP_AUTOMATION_EXECUTED.value,
    EventType.APP_AUTOMATION_FAILED.value,
}

SENSITIVE_KEY_FRAGMENTS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _event_store() -> EventStore:
    return EventStore(os.environ.get("APP_AUTOMATION_EVENTS_DIR") or os.environ.get("SESSIONS_DIR") or "/opt/workstation/sessions")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_sensitive(value: Any, *, key: str | None = None) -> Any:
    """Return a redacted JSON-safe copy of a value.

    The function intentionally redacts by key name before descending into nested
    values. It also truncates long strings so event payloads remain compact.
    """

    if key and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(child_key): redact_sensitive(child_value, key=str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:500] + "…"
    return value


def emit_app_automation_event(
    event_type: EventType,
    session_id: str | None,
    **data: Any,
) -> dict[str, Any] | None:
    """Append a redacted app-automation event when a session is available."""

    if not session_id:
        return None
    if event_type.value not in APP_AUTOMATION_EVENT_TYPES:
        raise ValueError(f"Unsupported app automation event type: {event_type.value}")
    event = create_event(event_type, session_id, **redact_sensitive(data))
    return _event_store().append(event).to_dict()


def list_app_automation_events(session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """Read redacted app automation events for one session."""

    events = _event_store().get_events(session_id, limit=limit, apply_observability_settings=False)
    return [event for event in events if event.get("event_type") in APP_AUTOMATION_EVENT_TYPES]
