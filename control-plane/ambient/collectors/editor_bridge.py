from __future__ import annotations

from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


def build_editor_selection_event(
    session_id: str,
    *,
    path: str,
    start_line: int,
    end_line: int,
    selected_text: str = "",
    symbol: str | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    repo_id: str | None = None,
    worktree_id: str | None = None,
    branch: str | None = None,
    confidence: float = 0.95,
) -> AmbientEvent:
    """Build an editor focus event from VS Code/code-server/Monaco/LSP state."""

    return AmbientEvent(
        event_type=AmbientEventType.EDITOR_SELECTION_CHANGED.value,
        session_id=session_id,
        source=AmbientSource.EDITOR,
        repo_id=repo_id,
        worktree_id=worktree_id,
        branch=branch,
        confidence=confidence,
        payload={
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "selected_text": selected_text[:8000],
            "symbol": symbol,
            "diagnostics": diagnostics or [],
        },
    )
