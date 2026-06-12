from __future__ import annotations

import re
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource
from ambient.vendor_registry import ensure_vendor_python_path, provider_available

MENTIONED_FILE_RE = re.compile(
    r"(?P<path>(?:[\w.\-]+/)+[\w.\-]+\.(?:py|ts|tsx|js|jsx|json|md|css|html|yaml|yml)|[\w.\-]+\.(?:py|ts|tsx|js|jsx|json|md|css|html|yaml|yml))"
)


class TerminalObservationBuilder:
    """Build structured terminal events from command-boundary telemetry.

    The preferred collection path is shell integration or PTY wrappers that know
    cwd, command start/end, stdout/stderr, exit code, and process duration. This
    builder turns that structured data into ambient events. When vendored pyte is
    available, it also reconstructs a bounded terminal screen tail from captured
    output.
    """

    def command_started(
        self,
        session_id: str,
        *,
        terminal_id: str,
        cwd: str,
        command: str,
        repo_id: str | None = None,
        worktree_id: str | None = None,
        branch: str | None = None,
    ) -> AmbientEvent:
        return AmbientEvent(
            event_type=AmbientEventType.TERMINAL_COMMAND_STARTED.value,
            session_id=session_id,
            source=AmbientSource.TERMINAL,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=branch,
            payload={
                "terminal_id": terminal_id,
                "cwd": cwd,
                "command": command,
            },
        )

    def command_completed(
        self,
        session_id: str,
        *,
        terminal_id: str,
        cwd: str,
        command: str,
        exit_code: int,
        duration_ms: int | None = None,
        stdout: str = "",
        stderr: str = "",
        repo_id: str | None = None,
        worktree_id: str | None = None,
        branch: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AmbientEvent:
        combined = "\n".join(part for part in (stdout, stderr) if part)
        mentioned_files = sorted(set(match.group("path") for match in MENTIONED_FILE_RE.finditer(combined)))
        screen_tail = reconstruct_terminal_screen_tail(combined)
        payload: dict[str, Any] = {
            "terminal_id": terminal_id,
            "cwd": cwd,
            "command": command,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
            "mentioned_files": mentioned_files,
            "failure_summary": summarize_failure(exit_code, stderr or stdout),
            "screen_provider": "pyte" if screen_tail else "plain_text",
            "screen_tail": screen_tail or combined[-4000:],
        }
        if extra:
            payload.update(extra)
        return AmbientEvent(
            event_type=AmbientEventType.TERMINAL_COMMAND_COMPLETED.value,
            session_id=session_id,
            source=AmbientSource.TERMINAL,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=branch,
            confidence=1.0 if exit_code == 0 else 0.95,
            payload=payload,
        )


def reconstruct_terminal_screen_tail(output: str, *, columns: int = 120, lines: int = 40) -> str:
    if not output or not provider_available("pyte", "pyte"):
        return ""
    ensure_vendor_python_path("pyte")
    try:
        import pyte
    except Exception:
        return ""
    try:
        screen = pyte.Screen(columns, lines)
        stream = pyte.Stream(screen)
        stream.feed(output[-12000:])
        return "\n".join(screen.display).rstrip()
    except Exception:
        return ""


def summarize_failure(exit_code: int, output: str) -> str | None:
    if exit_code == 0:
        return None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for marker in ("Error:", "FAILED", "AssertionError", "Traceback", "Exception"):
        for line in lines:
            if marker in line:
                return line[:240]
    return lines[-1][:240] if lines else f"Command failed with exit code {exit_code}"
