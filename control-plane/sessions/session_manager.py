"""
Shared session and worktree lifecycle helpers for the control plane.

This module is the source of truth for session directory metadata and git
worktree creation/removal. API and CLI entrypoints should call this module
instead of duplicating filesystem and subprocess logic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
REPOS_DIR = Path(os.environ.get("REPOS_DIR", "/opt/workstation/repos"))
BENCH_APPS_DIR = Path(os.environ.get("BENCH_APPS_DIR", "/opt/workstation/bench-apps"))


class SessionError(RuntimeError):
    """Base error for session lifecycle failures."""


class SessionAlreadyExists(SessionError):
    """Raised when creating a session that already exists."""


class SessionNotFound(SessionError):
    """Raised when a requested session does not exist."""


@dataclass
class SessionCreateRequest:
    name: str | None = None
    repo: str | None = None
    branch: str | None = None
    ports: str | None = None
    profile: str | None = None
    task: str | None = None


def _session_dir(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def resolve_repo_path(raw_repo: str | None) -> str:
    """Resolve a repo name or absolute path into the path stored in metadata."""
    repo = raw_repo or "example-react-app"

    for search_dir in (REPOS_DIR, BENCH_APPS_DIR):
        candidate = search_dir / repo
        if candidate.exists() and (candidate / ".git").exists():
            return str(candidate)

    raw_path = Path(repo)
    if raw_path.is_absolute() and raw_path.exists():
        return str(raw_path)

    return str(REPOS_DIR / repo)


def list_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    if not SESSIONS_DIR.exists():
        return sessions

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        meta_file = session_dir / "session.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text())
            ctx_dir = session_dir / "context"
            meta["has_ui_context"] = (ctx_dir / "latest-ui-context.md").exists()
            meta["has_editor_context"] = (ctx_dir / "latest-editor-context.md").exists()
            meta["has_terminal_context"] = (ctx_dir / "latest-terminal-context.md").exists()
            sessions.append(meta)
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    session_id = request.name or f"session-{int(time.time())}"
    repo_path = resolve_repo_path(request.repo)
    branch = request.branch or f"{session_id}-branch"

    session_dir = _session_dir(session_id)
    if session_dir.exists():
        raise SessionAlreadyExists(f"Session '{session_id}' already exists")

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "context").mkdir(exist_ok=True)
    (session_dir / "events").mkdir(exist_ok=True)

    worktree_path = str(REPOS_DIR / f"worktree-{session_id}")
    repo = Path(repo_path)
    if repo.exists() and (repo / ".git").exists():
        result = subprocess.run(
            ["git", "worktree", "add", worktree_path, "-b", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "worktree", "add", worktree_path, branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

    meta = {
        "id": session_id,
        "repo_path": repo_path,
        "worktree_path": worktree_path,
        "branch": branch,
        "port_range": request.ports or "",
        "browser_profile": request.profile or session_id,
        "tmux_session": f"agent-{session_id}",
        "status": "active",
        "task": request.task or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(session_dir / "session.json", "w") as f:
        json.dump(meta, f, indent=2)

    return meta


def destroy_session(session_id: str) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    if not session_dir.exists():
        raise SessionNotFound(f"Session '{session_id}' not found")

    meta_file = session_dir / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        worktree_path = meta.get("worktree_path", "")
        repo_path = meta.get("repo_path", "")
        if worktree_path and Path(worktree_path).exists():
            subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                cwd=repo_path or None,
                capture_output=True,
            )

    shutil.rmtree(session_dir)
    return {"status": "destroyed", "session_id": session_id}


def inspect_session(session_id: str, context_limit: int | None = None) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    if not session_dir.exists():
        raise SessionNotFound(f"Session '{session_id}' not found")

    meta = json.loads((session_dir / "session.json").read_text())
    context = get_session_context(session_id)["context"]
    if context_limit is not None:
        context = {
            name: value[:context_limit] if isinstance(value, str) else value
            for name, value in context.items()
        }
    meta["context"] = context
    return meta


def get_session_context(session_id: str) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    if not session_dir.exists():
        raise SessionNotFound(f"Session '{session_id}' not found")

    ctx_dir = session_dir / "context"
    result: dict[str, str] = {}
    for ctx_file in [
        "latest-ui-context.md",
        "latest-editor-context.md",
        "latest-terminal-context.md",
    ]:
        path = ctx_dir / ctx_file
        if path.exists():
            result[ctx_file.replace("latest-", "").replace("-context.md", "")] = path.read_text()

    events_dir = session_dir / "events"
    events: dict[str, list[dict[str, Any]]] = {}
    for ev_file in events_dir.glob("*.jsonl"):
        lines = ev_file.read_text().strip().split("\n")
        events[ev_file.stem] = [json.loads(line) for line in lines[-20:] if line.strip()]

    return {"context": result, "events": events}
