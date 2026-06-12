from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AmbientSource(str, Enum):
    BROWSER = "browser"
    FRONTEND = "frontend"
    EDITOR = "editor"
    TERMINAL = "terminal"
    REPO = "repo"
    DESKTOP = "desktop"
    RUNTIME_TRACE = "runtime_trace"
    SCREENSHOT_FALLBACK = "screenshot_fallback"
    TEST = "test"


class AmbientEventType(str, Enum):
    BROWSER_TAB_OBSERVED = "browser.tab_observed"
    BROWSER_ELEMENT_SELECTED = "browser.element_selected"
    BROWSER_CONSOLE_LOG = "browser.console_log"
    BROWSER_NETWORK_REQUEST = "browser.network_request"
    FRONTEND_INTERACTION = "frontend.interaction"
    EDITOR_SELECTION_CHANGED = "editor.selection_changed"
    TERMINAL_COMMAND_STARTED = "terminal.command_started"
    TERMINAL_COMMAND_COMPLETED = "terminal.command_completed"
    REPO_STATE_OBSERVED = "repo.state_observed"
    REPO_FILES_CHANGED = "repo.files_changed"
    DESKTOP_WINDOW_FOCUSED = "desktop.window_focused"
    RUNTIME_REQUEST_OBSERVED = "runtime.request_observed"
    RUNTIME_TRACE_OBSERVED = "runtime.trace_observed"
    CONTEXT_PACKET_BUILT = "context.packet_built"
    SCREENSHOT_FALLBACK_CAPTURED = "screenshot.fallback_captured"


class PrivacyMark(BaseModel):
    contains_secret: bool = False
    redaction_applied: bool = False
    redacted_fields: list[str] = Field(default_factory=list)


class AmbientEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"amb_{uuid.uuid4().hex}")
    event_type: str
    session_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: AmbientSource | str
    actor: Literal["user", "agent", "system", "collector"] = "collector"
    root_session_id: str | None = None
    repo_id: str | None = None
    worktree_id: str | None = None
    branch: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    privacy: PrivacyMark = Field(default_factory=PrivacyMark)
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceNode(BaseModel):
    node_id: str
    kind: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdge(BaseModel):
    source_id: str
    target_id: str
    relation: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphSnapshot(BaseModel):
    session_id: str
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)


class ContextPacket(BaseModel):
    session_id: str
    goal: str | None = None
    repo_id: str | None = None
    worktree_id: str | None = None
    branch: str | None = None
    ambient_focus: dict[str, Any] | None = None
    latest: dict[str, Any] = Field(default_factory=dict)
    recent_observations: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    privacy: PrivacyMark = Field(default_factory=PrivacyMark)
