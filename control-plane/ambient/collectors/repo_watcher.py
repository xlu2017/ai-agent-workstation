from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


class RepoSnapshotCollector:
    """Collect repo/worktree state.

    Preferred live path: watchfiles for file-change batches plus git snapshotting.
    Dependency-free scaffold path: `git status --porcelain` and `git rev-parse`.
    """

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)

    def snapshot(self) -> dict[str, Any]:
        branch = self._git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or None
        commit = self._git(["rev-parse", "HEAD"]).strip() or None
        status = self._git(["status", "--porcelain=v1"])
        dirty_files = []
        for line in status.splitlines():
            if not line.strip():
                continue
            dirty_files.append({"status": line[:2].strip(), "path": line[3:].strip()})
        return {
            "repo_root": str(self.repo_root),
            "branch": branch,
            "commit": commit,
            "dirty_files": dirty_files,
        }

    def build_event(
        self,
        session_id: str,
        *,
        repo_id: str | None = None,
        worktree_id: str | None = None,
    ) -> AmbientEvent:
        snap = self.snapshot()
        return AmbientEvent(
            event_type=AmbientEventType.REPO_STATE_OBSERVED.value,
            session_id=session_id,
            source=AmbientSource.REPO,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=snap.get("branch"),
            payload=snap,
        )

    def _git(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout


def build_files_changed_event(
    session_id: str,
    changes: list[dict[str, str]],
    *,
    repo_id: str | None = None,
    worktree_id: str | None = None,
    branch: str | None = None,
) -> AmbientEvent:
    """Build a file-change batch event from watchfiles or another watcher."""

    return AmbientEvent(
        event_type=AmbientEventType.REPO_FILES_CHANGED.value,
        session_id=session_id,
        source=AmbientSource.REPO,
        repo_id=repo_id,
        worktree_id=worktree_id,
        branch=branch,
        payload={"changes": changes},
    )
