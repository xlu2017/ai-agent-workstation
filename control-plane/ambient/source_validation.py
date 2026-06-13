from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambient.source_candidates import build_source_candidates
from ambient.types import AmbientEvent

DEFAULT_REPOS_DIR = Path("/opt/workstation/repos")


def validate_ambient_source_candidates(
    session_id: str,
    events: list[AmbientEvent],
    *,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    repos_dir: str | Path = DEFAULT_REPOS_DIR,
    max_candidates: int = 12,
) -> dict[str, Any]:
    """Validate ranked ambient source candidates against the session worktree.

    Ambient source candidates are evidence, not authority. This helper keeps that
    boundary explicit by checking whether each candidate path is syntactically
    safe, contained by the session worktree, and present on disk before any
    execution path treats it as actionable.
    """

    candidates = build_source_candidates(events, max_candidates=max_candidates)
    worktree_root = resolve_session_worktree(session_id, sessions_dir=sessions_dir, repos_dir=repos_dir)
    validations = [validate_source_candidate(candidate, worktree_root) for candidate in candidates]
    return {
        "session_id": session_id,
        "worktree_root": str(worktree_root) if worktree_root else "",
        "source_candidates": candidates,
        "validated_candidates": validations,
        "valid_count": sum(1 for item in validations if item["status"] == "valid"),
        "blocked_count": sum(1 for item in validations if item["status"] == "blocked"),
        "missing_count": sum(1 for item in validations if item["status"] == "missing"),
        "unverified_count": sum(1 for item in validations if item["status"] == "unverified"),
        "advisory_only": True,
        "requires_platform_validation": True,
    }


def validate_source_candidate(candidate: dict[str, Any], worktree_root: Path | None) -> dict[str, Any]:
    path_value = str(candidate.get("path") or "").strip()
    base = {
        "path": path_value,
        "line": candidate.get("line"),
        "symbol": candidate.get("symbol"),
        "confidence": candidate.get("confidence"),
        "reason": candidate.get("reason"),
        "event_id": candidate.get("event_id"),
        "source": candidate.get("source"),
        "contained": False,
        "exists": False,
        "resolved_path": "",
    }

    if not path_value:
        return {**base, "status": "blocked", "message": "Candidate path is empty."}
    if _looks_unsafe(path_value):
        return {**base, "status": "blocked", "message": "Candidate path is syntactically unsafe."}
    if worktree_root is None:
        return {**base, "status": "unverified", "message": "Session worktree could not be resolved."}

    try:
        root = worktree_root.resolve()
        candidate_path = Path(path_value)
        resolved = candidate_path.resolve() if candidate_path.is_absolute() else (root / candidate_path).resolve()
    except OSError as exc:
        return {**base, "status": "blocked", "message": f"Candidate path could not be resolved: {exc}"}

    contained = _is_relative_to(resolved, root)
    exists = resolved.exists()
    data = {
        **base,
        "contained": contained,
        "exists": exists,
        "resolved_path": str(resolved),
    }
    if not contained:
        return {**data, "status": "blocked", "message": "Candidate path escapes the session worktree."}
    if not exists:
        return {**data, "status": "missing", "message": "Candidate path is contained but does not exist."}
    return {**data, "status": "valid", "message": "Candidate path is contained in the session worktree and exists."}


def resolve_session_worktree(
    session_id: str,
    *,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    repos_dir: str | Path = DEFAULT_REPOS_DIR,
) -> Path | None:
    meta = _load_session_meta(session_id, sessions_dir)
    if not meta:
        return None

    explicit = meta.get("worktree_path") or meta.get("workspace_path")
    if isinstance(explicit, str) and explicit.strip():
        return Path(explicit.strip())

    worktree_id = meta.get("worktree_id") or meta.get("worktree")
    if isinstance(worktree_id, str) and worktree_id.strip():
        path = Path(worktree_id.strip())
        if path.is_absolute():
            return path
        return Path(repos_dir) / path

    repo_id = meta.get("repo_id")
    if isinstance(repo_id, str) and repo_id.strip():
        path = Path(repo_id.strip())
        if path.is_absolute():
            return path
        return Path(repos_dir) / path

    return None


def _load_session_meta(session_id: str, sessions_dir: str | Path) -> dict[str, Any] | None:
    session_dir = Path(sessions_dir) / session_id
    for filename in ("session-meta.json", "session.json"):
        path = session_dir / filename
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _looks_unsafe(path_value: str) -> bool:
    if "\x00" in path_value or "\n" in path_value or "\r" in path_value:
        return True
    parts = Path(path_value).parts
    return ".." in parts


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
