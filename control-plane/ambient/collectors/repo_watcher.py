from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource
from ambient.vendor_registry import ensure_vendor_python_path, provider_available


class RepoSnapshotCollector:
    """Collect repo/worktree state without assuming a stable worktree path."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)

    def snapshot(self) -> dict[str, Any]:
        exists = self.repo_root.exists()
        is_git = exists and ((self.repo_root / ".git").exists() or bool(self._git(["rev-parse", "--git-dir"])))
        if not exists or not is_git:
            return {
                "repo_root": str(self.repo_root),
                "available": False,
                "provider": "git_status",
                "exists": exists,
                "is_git": is_git,
                "branch": None,
                "commit": None,
                "dirty_files": [],
                "watchfiles_available": provider_available("watchfiles", "watchfiles"),
            }

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
            "available": True,
            "provider": "git_status",
            "exists": True,
            "is_git": True,
            "branch": branch,
            "commit": commit,
            "dirty_files": dirty_files,
            "watchfiles_available": provider_available("watchfiles", "watchfiles"),
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
            confidence=0.95 if snap.get("available") else 0.25,
            payload=snap,
        )

    def poll_file_changes_once(self, *, timeout_ms: int = 1000) -> list[dict[str, str]]:
        """Collect a one-shot watchfiles batch when the provider is available.

        This is intentionally optional. The normal collection path still records
        git status, while long-running watchers can call this method to get live
        file change events without importing watchfiles at process start.
        """

        if not self.repo_root.exists() or not provider_available("watchfiles", "watchfiles"):
            return []
        ensure_vendor_python_path("watchfiles")
        try:
            from watchfiles import watch
        except Exception:
            return []
        try:
            for changes in watch(str(self.repo_root), stop_event=None, yield_on_timeout=True, rust_timeout=timeout_ms):
                result = []
                for change, path in changes:
                    result.append({"change": str(change), "path": str(Path(path))})
                return result
        except Exception:
            return []
        return []

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
        payload={"changes": changes, "provider": "watchfiles" if provider_available("watchfiles", "watchfiles") else "external"},
    )
