from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ambient.redaction import redact_payload
from ambient.types import AmbientEvent, AmbientEventType


def _ambient_dir(sessions_dir: str | Path, session_id: str) -> Path:
    path = Path(sessions_dir) / session_id / "ambient"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ambient_events_file(sessions_dir: str | Path, session_id: str) -> Path:
    return _ambient_dir(sessions_dir, session_id) / "events.jsonl"


def _next_sequence(path: Path) -> int:
    if not path.exists():
        return 1
    return sum(1 for _ in path.open()) + 1


def persist_ambient_event(
    event: AmbientEvent,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    mirror_live_feed: bool = True,
) -> AmbientEvent:
    """Persist a redacted ambient event.

    Ambient events are stored in a rich ambient log and optionally mirrored into
    the canonical live-feed log as a safe summary. The mirror event is for UI and
    timeline awareness; the ambient log remains the richer evidence source.
    """

    payload, privacy = redact_payload(event.payload)
    event.payload = payload
    event.privacy = privacy

    path = _ambient_events_file(sessions_dir, event.session_id)
    data = event.model_dump()
    data["ambient_sequence"] = _next_sequence(path)
    with path.open("a") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")

    if mirror_live_feed:
        _mirror_to_live_feed(event, sessions_dir)
    return event


def _mirror_to_live_feed(event: AmbientEvent, sessions_dir: str | Path) -> None:
    try:
        from live_feed.events import EventStore, EventType, create_event
    except Exception:
        return

    if not hasattr(EventType, "AMBIENT_CONTEXT_COLLECTED"):
        return

    summary = {
        "ambient_event_id": event.event_id,
        "ambient_event_type": event.event_type,
        "source": str(event.source),
        "confidence": event.confidence,
        "privacy": event.privacy.model_dump(),
        "summary": summarize_ambient_event(event),
    }
    store = EventStore(sessions_dir)
    store.append(create_event(EventType.AMBIENT_CONTEXT_COLLECTED, event.session_id, **summary))


def load_ambient_events(
    session_id: str,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    limit: int | None = None,
) -> list[AmbientEvent]:
    path = _ambient_events_file(sessions_dir, session_id)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit is not None:
        rows = rows[-limit:]
    return [AmbientEvent.model_validate(row) for row in rows]


def summarize_ambient_event(event: AmbientEvent) -> str:
    payload = event.payload
    event_type = str(event.event_type)
    if event_type == AmbientEventType.BROWSER_ELEMENT_SELECTED.value:
        label = payload.get("text") or payload.get("selector") or "browser element"
        source = payload.get("component", {}).get("source") or payload.get("url")
        return f"Selected {label} ({source})" if source else f"Selected {label}"
    if event_type == AmbientEventType.TERMINAL_COMMAND_COMPLETED.value:
        command = payload.get("command", "command")
        exit_code = payload.get("exit_code")
        return f"Command completed: {command} exit={exit_code}"
    if event_type == AmbientEventType.REPO_STATE_OBSERVED.value:
        branch = payload.get("branch", "unknown")
        dirty = len(payload.get("dirty_files", []))
        return f"Repo state observed on {branch} with {dirty} dirty files"
    if event_type == AmbientEventType.DESKTOP_WINDOW_FOCUSED.value:
        title = payload.get("window_title") or payload.get("window_class") or "window"
        return f"Focused desktop window: {title}"
    if event_type == AmbientEventType.RUNTIME_REQUEST_OBSERVED.value:
        method = payload.get("method", "HTTP")
        path = payload.get("path", payload.get("url", "request"))
        status = payload.get("status_code", "?")
        return f"Observed {method} {path} -> {status}"
    return event_type.replace(".", " ")


def persist_many(
    events: Iterable[AmbientEvent],
    sessions_dir: str | Path = "/opt/workstation/sessions",
) -> list[AmbientEvent]:
    return [persist_ambient_event(event, sessions_dir=sessions_dir) for event in events]
