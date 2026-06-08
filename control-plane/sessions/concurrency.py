"""
Concurrency rules for multi-session worktree isolation.

Rules:
  1. One mutating executor per worktree.
  2. Parallel read-only sessions may share a repo checkout.
  3. Parallel mutating sessions require separate worktrees.
  4. Commits require platform validation.
  5. PRs require platform validation.
  6. If two sessions touch overlapping files, surface a conflict event.

This module answers: "Can this session safely use this worktree?"
It does NOT own execution or git operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sessions.models import Session, SessionStatus, SessionStore, SessionType


@dataclass
class WorktreeClaimResult:
    allowed: bool
    reason: str
    worktree_id: str = ""
    conflict_session_id: str = ""
    conflict_files: list[str] = field(default_factory=list)


@dataclass
class ConflictEvent:
    session_a: str
    session_b: str
    worktree_id: str
    overlapping_files: list[str]
    severity: str = "warning"  # warning, error


class ConcurrencyManager:
    """Manages worktree claims and conflict detection."""

    def __init__(self, session_store: SessionStore):
        self.session_store = session_store
        # In-memory tracking of active worktree claims
        # worktree_id → { session_id, mode, files }
        self._claims: dict[str, dict[str, Any]] = {}

    def claim_worktree(
        self,
        session_id: str,
        worktree_id: str,
        mode: str = "mutating",  # mutating or read_only
        initial_files: list[str] | None = None,
    ) -> WorktreeClaimResult:
        """Attempt to claim a worktree for a session.

        mutating: exclusive — only one per worktree
        read_only: shared — multiple sessions allowed
        """
        existing = self._claims.get(worktree_id)

        if existing is None:
            self._claims[worktree_id] = {
                "session_id": session_id,
                "mode": mode,
                "files": set(initial_files or []),
            }
            return WorktreeClaimResult(
                allowed=True,
                reason=f"Worktree {worktree_id} claimed by {session_id} ({mode}).",
                worktree_id=worktree_id,
            )

        # Read-only can always share
        if mode == "read_only" and existing["mode"] == "read_only":
            return WorktreeClaimResult(
                allowed=True,
                reason="Read-only sharing permitted.",
                worktree_id=worktree_id,
            )

        # Read-only can share with mutating (it won't write)
        if mode == "read_only":
            return WorktreeClaimResult(
                allowed=True,
                reason="Read-only access alongside mutating session permitted.",
                worktree_id=worktree_id,
            )

        # Mutating + mutating = conflict
        if existing["mode"] == "mutating":
            return WorktreeClaimResult(
                allowed=False,
                reason=f"Worktree {worktree_id} already claimed by mutating session {existing['session_id']}.",
                worktree_id=worktree_id,
                conflict_session_id=existing["session_id"],
            )

        # Mutating over read-only = allowed (upgrade)
        self._claims[worktree_id] = {
            "session_id": session_id,
            "mode": mode,
            "files": set(initial_files or []),
        }
        return WorktreeClaimResult(
            allowed=True,
            reason=f"Worktree {worktree_id} upgraded to mutating by {session_id}.",
            worktree_id=worktree_id,
        )

    def release_worktree(self, session_id: str, worktree_id: str) -> bool:
        """Release a worktree claim."""
        existing = self._claims.get(worktree_id)
        if existing and existing["session_id"] == session_id:
            del self._claims[worktree_id]
            return True
        return False

    def check_file_conflict(
        self,
        session_id: str,
        worktree_id: str,
        files: list[str],
    ) -> ConflictEvent | None:
        """Check if files overlap with another session's active files."""
        existing = self._claims.get(worktree_id)
        if existing is None or existing["session_id"] == session_id:
            return None

        overlap = set(files) & existing["files"]
        if overlap:
            return ConflictEvent(
                session_a=session_id,
                session_b=existing["session_id"],
                worktree_id=worktree_id,
                overlapping_files=sorted(overlap),
            )
        return None

    def register_files(
        self, session_id: str, worktree_id: str, files: list[str]
    ) -> None:
        """Register files being touched by a session."""
        existing = self._claims.get(worktree_id)
        if existing and existing["session_id"] == session_id:
            existing["files"].update(files)

    def get_active_claims(self) -> dict[str, dict[str, Any]]:
        """Return all active worktree claims."""
        return {
            wt_id: {
                "session_id": claim["session_id"],
                "mode": claim["mode"],
                "files": sorted(claim["files"]),
            }
            for wt_id, claim in self._claims.items()
        }

    def suggest_worktree(
        self, session: Session, repos_dir: str = "/opt/workstation/repos"
    ) -> str:
        """Suggest a worktree ID for a new session.

        If the session's repo already has a mutating claim, suggest a new
        worktree. Otherwise reuse the repo checkout.
        """
        # Check if any existing claim on this repo's worktrees
        for wt_id, claim in self._claims.items():
            if claim["mode"] == "mutating":
                # This worktree is claimed; suggest a new one
                pass

        # Default: create a new worktree
        return f"worktree-{session.session_id}"
