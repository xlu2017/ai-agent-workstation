"""
Canonical execution result and event contracts.

All executors (AgenticExecutor, DeterministicExecutor) return ExecutionResult.
All executor-emitted events use ExecutionEvent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionEvent:
    """Normalized event emitted by an executor during action execution."""

    event_type: str  # action_progress | command_executed | file_read | file_edited | file_created | test_completed | agent_error
    title: str
    summary: str
    status: str = "running"  # running | completed | failed | blocked | skipped
    metadata: dict[str, Any] = field(default_factory=dict)
    redacted: bool = True
    source: str = ""  # agentic | deterministic

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "metadata": self.metadata,
            "redacted": self.redacted,
            "source": self.source,
        }


@dataclass
class ExecutionResult:
    """Canonical result shape returned by all executors."""

    status: str  # succeeded | failed | blocked | skipped | cancelled | needs_review
    backend: str  # agentic | deterministic
    summary: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    files_touched: list[str] = field(default_factory=list)
    events: list[ExecutionEvent] = field(default_factory=list)
    duration_ms: int = 0
    redacted: bool = True
    fallback_used: bool = False
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "backend": self.backend,
            "summary": self.summary,
            "output": self.output,
            "error": self.error,
            "files_touched": self.files_touched,
            "events": [e.to_dict() for e in self.events],
            "duration_ms": self.duration_ms,
            "redacted": self.redacted,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }

    # Dict-like access for backward compatibility
    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)
