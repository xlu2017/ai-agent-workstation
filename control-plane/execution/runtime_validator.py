"""
Runtime validator — platform-side validation before action execution.

Validates:
  1. Session exists
  2. Worktree_id exists
  3. Worktree path exists
  4. Action appears in session.allowed_actions
  5. Path params do not escape worktree
  6. Commit action requires commit to be in allowed_actions
  7. Commit action requires non-empty message
  8. Composite action requires LANGGRAPH_ENABLED=true unless fallback composite allowed

This is runtime/platform validation, separate from agent-core schema validation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adapters.composite_action.base import is_composite_action
from sessions.models import Session, SessionStore


LANGGRAPH_ENABLED = os.environ.get("LANGGRAPH_ENABLED", "false").lower() == "true"
ALLOW_FALLBACK_COMPOSITE = (
    os.environ.get("ALLOW_FALLBACK_COMPOSITE_ACTIONS", "false").lower() == "true"
)


@dataclass
class ValidationResult:
    allowed: bool
    reason: str = ""
    normalized_params: dict[str, Any] = field(default_factory=dict)


class RuntimeValidator:
    """Validate actions before execution at the platform level."""

    def __init__(
        self,
        session_store: SessionStore,
        worktree_base: str | Path = "/opt/workstation/repos",
        langgraph_enabled: bool | None = None,
        allow_fallback_composite: bool | None = None,
    ):
        self.session_store = session_store
        self.worktree_base = Path(worktree_base)
        self._langgraph_enabled = (
            langgraph_enabled if langgraph_enabled is not None else LANGGRAPH_ENABLED
        )
        self._allow_fallback_composite = (
            allow_fallback_composite
            if allow_fallback_composite is not None
            else ALLOW_FALLBACK_COMPOSITE
        )

    def validate(
        self,
        session_id: str,
        action_name: str,
        params: dict[str, Any],
    ) -> ValidationResult:
        """Validate an action before execution."""

        # 1. Session exists
        session = self.session_store.get(session_id)
        if session is None:
            return ValidationResult(
                allowed=False, reason=f"Session {session_id} not found"
            )

        # 2. Worktree exists in session
        if not session.worktree_id:
            # Some actions (like search_memory) don't need a worktree
            pass

        # 3. Worktree path exists on disk (if worktree_id set)
        if session.worktree_id:
            wt_path = self.worktree_base / session.worktree_id
            if not wt_path.exists():
                return ValidationResult(
                    allowed=False,
                    reason=f"Worktree path does not exist: {wt_path}",
                )

        # 4. Action in allowed_actions
        if session.allowed_actions and action_name not in session.allowed_actions:
            return ValidationResult(
                allowed=False,
                reason=f"Action {action_name} is not in session allowed_actions",
            )

        # 5. Path params do not escape worktree
        if session.worktree_id:
            wt_path = self.worktree_base / session.worktree_id
            path_escape = self._check_path_escape(wt_path, params)
            if path_escape:
                return ValidationResult(allowed=False, reason=path_escape)

        # 6. Commit requires commit in allowed_actions
        if action_name == "commit":
            if "commit" not in (session.allowed_actions or []):
                return ValidationResult(
                    allowed=False,
                    reason="Commit action requires commit to be in allowed_actions",
                )

        # 7. Commit requires non-empty message
        if action_name == "commit":
            message = params.get("message", "")
            if not message.strip():
                return ValidationResult(
                    allowed=False,
                    reason="Commit action requires a non-empty message",
                )

        # 8. Composite action requires LangGraph or fallback
        if is_composite_action(action_name):
            if not self._langgraph_enabled and not self._allow_fallback_composite:
                return ValidationResult(
                    allowed=False,
                    reason=(
                        f"Composite action {action_name} requires "
                        "LANGGRAPH_ENABLED=true or ALLOW_FALLBACK_COMPOSITE_ACTIONS=true"
                    ),
                )

        # Normalize params
        normalized = dict(params)
        return ValidationResult(allowed=True, normalized_params=normalized)

    def _check_path_escape(
        self, worktree: Path, params: dict[str, Any]
    ) -> str:
        """Check if any path-like params escape the worktree."""
        path_keys = ["path", "file", "target", "directory"]
        wt_resolved = worktree.resolve()

        for key in path_keys:
            if key in params and isinstance(params[key], str):
                candidate = params[key]
                if not candidate:
                    continue
                resolved = (worktree / candidate).resolve()
                if not str(resolved).startswith(str(wt_resolved)):
                    return f"Path escapes worktree: {key}={candidate}"
        return ""
