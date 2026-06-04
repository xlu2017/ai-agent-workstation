"""Typed queue payloads for platform agent-session tasks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ExecutorName = Literal["openhands", "direct"]


class PlatformTaskInput(BaseModel):
    """Input payload scheduled onto the platform task queue."""

    task_id: str
    session_id: str
    instruction: str
    worktree_path: str
    branch: str
    executor: ExecutorName = "openhands"
    model: str = "deepseek-v4-flash"
    risk_level: Literal["low", "medium", "high"] = "low"
    ui_context: str | None = None
    editor_context: str | None = None
    terminal_context: str | None = None
    activated_knowledge: list[dict[str, Any]] = Field(default_factory=list)
    staleness_warnings: list[str] = Field(default_factory=list)


class PlatformTaskOutput(BaseModel):
    """Result returned by a platform task worker."""

    status: str
    task_id: str
    session_id: str
    executor: ExecutorName
    files_edited: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    commit_sha: str | None = None
    error: str | None = None
    summary: str = ""
    cost_usd: float = 0.0
    duration_seconds: float = 0.0


class QueueSubmitResult(BaseModel):
    """Response returned by queue submitters."""

    queued: bool
    queue_backend: Literal["hatchet", "local"]
    task_id: str
    session_id: str
    run_id: str | None = None
    message: str = ""
