"""
ExecutionAdapter interface — low-level action execution abstraction.

Implementations:
  OpenHandsExecutorAdapter  — primary coding execution backend
  FallbackExecutorAdapter   — dev/test/simple local fallback only
"""

from __future__ import annotations

import abc
from typing import Any


class ExecutionAdapter(abc.ABC):
    """Abstract base for action execution backends."""

    @abc.abstractmethod
    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single action in a worktree.

        Returns:
            {
                status: succeeded | failed | blocked | skipped,
                backend: openhands | fallback,
                output: {},
                error: "",
                files_touched: [],
                duration_ms: int,
            }
        """
        ...
