"""
Runtime validator — platform-side validation before action execution.

Validates:
  1. Session exists
  2. Worktree_id exists
  3. Worktree path exists
  4. Action appears in session.allowed_actions
  5. Path params do not escape worktree
  6. High-risk actions require session-scoped gate evidence
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
from execution.approval_store import gate_is_valid
from sessions.models import SessionStore


LANGGRAPH_ENABLED = os.environ.get("LANGGRAPH_ENABLED", "false").lower() == "true"
ALLOW_FALLBACK_COMPOSITE = (
    os.environ.get("ALLOW_FALLBACK_COMPOSITE_ACTIONS", "false").lower() == "true"
)

GATED_ACTIONS = {
    "commit",
    "push_branch",
    "create_pr",
    "merge_pr",
    "stop_service",
    "update_latest_from_github",
}

PATH_KEYS = {"path", "file", "target", "directory", "output_path", "repo_path"}
PATH_LIST_KEYS = {"paths", "files", "directories"}


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

        # 2-3. Worktree path exists on disk when the action needs a worktree.
        wt_path: Path | None = None
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
        if wt_path is not None:
            path_escape = self._check_path_escape(wt_path, params)
            if path_escape:
                return ValidationResult(allowed=False, reason=path_escape)

        # 6. High-risk actions require gate evidence.
        if action_name in GATED_ACTIONS:
            gate_id = str(
                params.get("gate_id")
                or params.get("approval_id")
                or params.get("approval_token")
                or ""
            )
            sessions_dir = getattr(self.session_store, "sessions_dir", "/opt/workstation/sessions")
            ok, reason = gate_is_valid(sessions_dir, session_id, action_name, gate_id)
            if not ok:
                return ValidationResult(allowed=False, reason=reason)

        # 7. Commit requires non-empty message
        if action_name == "commit":
            message = params.get("message", "")
            if not isinstance(message, str) or not message.strip():
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

        normalized = dict(params)
        return ValidationResult(allowed=True, normalized_params=normalized)

    def _check_path_escape(self, worktree: Path, params: dict[str, Any]) -> str:
        """Recursively check path-like params against the resolved worktree."""
        wt_resolved = worktree.resolve()

        def check_candidate(key: str, value: str) -> str:
            if not value:
                return ""
            candidate = Path(value)
            resolved = candidate.resolve() if candidate.is_absolute() else (worktree / candidate).resolve()
            try:
                resolved.relative_to(wt_resolved)
            except ValueError:
                return f"Path escapes worktree: {key}={value}"
            return ""

        def walk(value: Any, key: str = "") -> str:
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    if child_key in PATH_KEYS and isinstance(child_value, str):
                        issue = check_candidate(child_key, child_value)
                        if issue:
                            return issue
                    if child_key in PATH_LIST_KEYS and isinstance(child_value, list):
                        for item in child_value:
                            if isinstance(item, str):
                                issue = check_candidate(child_key, item)
                                if issue:
                                    return issue
                    issue = walk(child_value, child_key)
                    if issue:
                        return issue
            elif isinstance(value, list):
                for item in value:
                    issue = walk(item, key)
                    if issue:
                        return issue
            return ""

        return walk(params)
