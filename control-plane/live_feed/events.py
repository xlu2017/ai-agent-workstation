"""
Event stream model for session execution.

Each session has an append-only event log. Events are the single source of truth
for what happened during execution. The status narrator (status_feed/narrator.py)
derives user-facing messages; this module owns the raw event types and storage.

Event types follow the spec:
  user_prompt_received, routing_decision_made, plan_requested, plan_generated,
  plan_validation_failed, plan_started, action_started, action_progress,
  action_blocked, action_completed, action_failed, plan_paused, plan_resumed,
  plan_cancelled, plan_completed, child_session_started, memory_extracted,
  commit_created, pr_created

Ambient context events are mirrored here only as safe summaries. Rich ambient
payloads live under <sessions_dir>/<session_id>/ambient/events.jsonl.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(str, Enum):
    USER_PROMPT_RECEIVED = "user_prompt_received"
    ROUTING_DECISION_MADE = "routing_decision_made"
    PLAN_REQUESTED = "plan_requested"
    PLAN_GENERATED = "plan_generated"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"
    PLAN_STARTED = "plan_started"
    ACTION_STARTED = "action_started"
    ACTION_PROGRESS = "action_progress"
    ACTION_BLOCKED = "action_blocked"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"
    PLAN_PAUSED = "plan_paused"
    PLAN_RESUMED = "plan_resumed"
    PLAN_CANCELLED = "plan_cancelled"
    PLAN_COMPLETED = "plan_completed"
    CHILD_SESSION_STARTED = "child_session_started"
    MEMORY_EXTRACTED = "memory_extracted"
    COMMIT_CREATED = "commit_created"
    PR_CREATED = "pr_created"
    WORKSPACE_PROVISIONED = "workspace_provisioned"

    # Granular workflow transcript event types
    TASK_STARTED = "task_started"
    TASK_CLASSIFIED = "task_classified"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TASK_BLOCKED = "task_blocked"
    TASK_CANCELLED = "task_cancelled"
    THOUGHT_ELAPSED = "thought_elapsed"
    FILE_READ = "file_read"
    CODE_SEARCHED = "code_searched"
    FILE_EDITED = "file_edited"
    COMMAND_RUN = "command_run"
    TEST_RUN = "test_run"
    VALIDATION_COMPLETED = "validation_completed"
    DIFF_SUMMARIZED = "diff_summarized"

    # App automation audit event types
    APP_AUTOMATION_PLANNED = "app_automation_planned"
    APP_AUTOMATION_VALIDATION_FAILED = "app_automation_validation_failed"
    APP_AUTOMATION_BLOCKED = "app_automation_blocked"
    APP_AUTOMATION_EXECUTED = "app_automation_executed"
    APP_AUTOMATION_FAILED = "app_automation_failed"

    # Ambient observation fabric mirror event types
    AMBIENT_CONTEXT_COLLECTED = "ambient_context_collected"
    AMBIENT_STATE_UPDATED = "ambient_state_updated"
    CONTEXT_PACKET_BUILT = "context_packet_built"
    SCREENSHOT_FALLBACK_CAPTURED = "screenshot_fallback_captured"


@dataclass
class SessionEvent:
    event_type: EventType
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    def to_sse(self) -> str:
        """Format as SSE data line."""
        return f"id: {self.event_id}\nevent: {self.event_type.value}\ndata: {json.dumps(self.to_dict())}\n\n"


class EventStore:
    """Append-only event store backed by JSONL files.

    Storage: <sessions_dir>/<session_id>/events/events.jsonl
    """

    def __init__(self, sessions_dir: str | Path = "/opt/workstation/sessions"):
        self.sessions_dir = Path(sessions_dir)

    def _events_file(self, session_id: str) -> Path:
        events_dir = self.sessions_dir / session_id / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        return events_dir / "events.jsonl"

    def _next_sequence(self, session_id: str) -> int:
        path = self._events_file(session_id)
        if not path.exists():
            return 1
        count = sum(1 for _ in path.open())
        return count + 1

    def append(self, event: SessionEvent) -> SessionEvent:
        """Append an event to the session log. Sets sequence number."""
        event.sequence = self._next_sequence(event.session_id)
        path = self._events_file(event.session_id)
        with path.open("a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")
        return event

    def get_events(
        self,
        session_id: str,
        after_sequence: int = 0,
        event_types: list[EventType] | None = None,
        limit: int | None = None,
        apply_observability_settings: bool = True,
    ) -> list[dict[str, Any]]:
        """Read events from the session log.

        By default, reads honor the persisted observability lookback and max-event
        settings. Callers that need archival reads can pass
        apply_observability_settings=False.
        """
        path = self._events_file(session_id)
        if not path.exists():
            return []

        settings = _safe_observability_settings() if apply_observability_settings else None
        effective_limit = limit or (settings.max_events_per_session if settings else 1000)
        cutoff = None
        if settings:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.lookback_hours)

        events = []
        for line in path.open():
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("sequence", 0) <= after_sequence:
                continue
            if event_types and evt.get("event_type") not in [t.value for t in event_types]:
                continue
            if cutoff and _event_timestamp(evt) and _event_timestamp(evt) < cutoff:
                continue
            if settings and not _event_allowed_by_logging_extent(evt, settings):
                continue
            events.append(evt)
            if len(events) >= effective_limit:
                break
        return events

    def get_latest_event(
        self, session_id: str, event_type: EventType | None = None
    ) -> dict[str, Any] | None:
        """Get the most recent event, optionally filtered by type."""
        path = self._events_file(session_id)
        if not path.exists():
            return None
        latest = None
        for line in path.open():
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and evt.get("event_type") != event_type.value:
                continue
            latest = evt
        return latest


def _safe_observability_settings():
    try:
        from api.services.platform_settings import get_observability_settings
        return get_observability_settings()
    except Exception:
        return None


def _event_timestamp(evt: dict[str, Any]) -> datetime | None:
    value = evt.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_allowed_by_logging_extent(evt: dict[str, Any], settings) -> bool:
    data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
    event_type = evt.get("event_type", "")
    if not settings.include_ambient_context and event_type in {
        EventType.AMBIENT_CONTEXT_COLLECTED.value,
        EventType.AMBIENT_STATE_UPDATED.value,
        EventType.CONTEXT_PACKET_BUILT.value,
        EventType.SCREENSHOT_FALLBACK_CAPTURED.value,
    }:
        return False
    if not settings.include_debug_prompts and ("llm_prompt" in data or event_type == EventType.PLAN_REQUESTED.value):
        data.pop("llm_prompt", None)
        data.pop("prompt", None)
    if not settings.include_tool_outputs and data.get("type") in {"tool_output", "plan_output"}:
        data.pop("output", None)
    if settings.logging_extent == "minimal" and event_type in {
        EventType.ACTION_PROGRESS.value,
        EventType.THOUGHT_ELAPSED.value,
        EventType.AMBIENT_CONTEXT_COLLECTED.value,
    }:
        return False
    return True


def create_event(
    event_type: EventType,
    session_id: str,
    **data: Any,
) -> SessionEvent:
    """Helper to create a SessionEvent."""
    return SessionEvent(
        event_type=event_type,
        session_id=session_id,
        data=data,
    )
