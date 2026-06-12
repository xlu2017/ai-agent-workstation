from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ambient.types import AmbientEvent, AmbientEventType, PrivacyMark


class AmbientState(BaseModel):
    session_id: str
    latest: dict[str, Any] = Field(default_factory=dict)
    current_focus: dict[str, Any] | None = None
    recent_event_ids: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    privacy: PrivacyMark = Field(default_factory=PrivacyMark)


def reduce_ambient_events(events: list[AmbientEvent]) -> AmbientState:
    if not events:
        return AmbientState(session_id="")

    session_id = events[-1].session_id
    state = AmbientState(session_id=session_id)
    redacted_fields: set[str] = set()

    for event in events:
        event_type = str(event.event_type)
        state.recent_event_ids.append(event.event_id)
        redacted_fields.update(event.privacy.redacted_fields)

        if event_type.startswith("browser."):
            state.latest["browser"] = event.model_dump()
        elif event_type.startswith("editor."):
            state.latest["editor"] = event.model_dump()
        elif event_type.startswith("terminal."):
            state.latest["terminal"] = event.model_dump()
        elif event_type.startswith("repo."):
            state.latest["repo"] = event.model_dump()
        elif event_type.startswith("desktop."):
            state.latest["desktop"] = event.model_dump()
        elif event_type.startswith("runtime."):
            state.latest["runtime"] = event.model_dump()
        elif event_type.startswith("screenshot."):
            state.latest["screenshot_fallback"] = event.model_dump()

        for path in _extract_files(event.payload):
            if path not in state.relevant_files:
                state.relevant_files.append(path)

    state.current_focus = choose_current_focus(events)
    state.privacy = PrivacyMark(
        contains_secret=bool(redacted_fields),
        redaction_applied=bool(redacted_fields),
        redacted_fields=sorted(redacted_fields),
    )
    return state


def choose_current_focus(events: list[AmbientEvent]) -> dict[str, Any] | None:
    """Choose the best focus object for vague prompts such as 'fix this'."""

    priority = [
        AmbientEventType.EDITOR_SELECTION_CHANGED.value,
        AmbientEventType.BROWSER_ELEMENT_SELECTED.value,
        AmbientEventType.TERMINAL_COMMAND_COMPLETED.value,
        AmbientEventType.RUNTIME_REQUEST_OBSERVED.value,
        AmbientEventType.DESKTOP_WINDOW_FOCUSED.value,
    ]
    for desired in priority:
        for event in reversed(events):
            if str(event.event_type) == desired:
                return {
                    "kind": desired,
                    "event_id": event.event_id,
                    "confidence": event.confidence,
                    "payload": event.payload,
                }
    return None


def _extract_files(payload: dict[str, Any]) -> list[str]:
    files: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and _looks_like_path(value) and value not in files:
            files.append(value)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            for key in ("path", "file", "source", "source_path"):
                add(value.get(key))
            for item in value.values():
                if isinstance(item, (dict, list)):
                    add(item)

    add(payload)
    return files


def _looks_like_path(value: str) -> bool:
    if len(value) > 240 or "\n" in value:
        return False
    return any(value.endswith(ext) for ext in (
        ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".html", ".yaml", ".yml"
    )) or "/" in value and "." in value.rsplit("/", 1)[-1]
