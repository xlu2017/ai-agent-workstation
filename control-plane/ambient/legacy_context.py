from __future__ import annotations

from pathlib import Path

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource

CONTEXT_FILES = {
    "latest-ui-context.md": (AmbientSource.BROWSER, "legacy.ui_context"),
    "latest-editor-context.md": (AmbientSource.EDITOR, "legacy.editor_context"),
    "latest-terminal-context.md": (AmbientSource.TERMINAL, "legacy.terminal_context"),
}


def collect_legacy_context_events(
    session_id: str,
    session_dir: Path,
    *,
    repo_id: str | None = None,
    worktree_id: str | None = None,
    branch: str | None = None,
) -> list[AmbientEvent]:
    """Convert existing latest-*-context.md files into ambient observations.

    This keeps the new system compatible with older server/agent versions that
    wrote markdown context files before structured ambient events existed.
    """

    context_dir = session_dir / "context"
    events: list[AmbientEvent] = []
    for filename, (source, legacy_kind) in CONTEXT_FILES.items():
        path = context_dir / filename
        if not path.exists():
            continue
        try:
            text = path.read_text(errors="replace")
            stat = path.stat()
        except OSError:
            continue
        events.append(
            AmbientEvent(
                event_type=AmbientEventType.FRONTEND_INTERACTION.value if source == AmbientSource.BROWSER else (
                    AmbientEventType.EDITOR_SELECTION_CHANGED.value if source == AmbientSource.EDITOR else AmbientEventType.TERMINAL_COMMAND_COMPLETED.value
                ),
                session_id=session_id,
                source=source,
                repo_id=repo_id,
                worktree_id=worktree_id,
                branch=branch,
                confidence=0.45,
                payload={
                    "legacy_kind": legacy_kind,
                    "path": str(path),
                    "mtime": stat.st_mtime,
                    "content_tail": text[-6000:],
                },
            )
        )
    return events
