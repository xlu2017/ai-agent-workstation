"""
ExecutionAdapter interface — low-level action execution abstraction.

Implementations:
  AgenticExecutor       — primary local agentic coding executor (LLM tool-calling loop)
  DeterministicExecutor — fast deterministic executor for simple local operations
"""

from __future__ import annotations

import abc
from typing import Any

from execution.results import ExecutionResult


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
    ) -> ExecutionResult:
        """Execute a single action in a worktree.

        Returns an ExecutionResult with normalized status, events, and output.
        """
        ...
