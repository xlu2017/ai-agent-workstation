"""
ExecutionRouter — selects the appropriate execution backend.

Rules:
  EXECUTOR_BACKEND=openhands  → OpenHandsExecutorAdapter
  EXECUTOR_BACKEND=fallback   → FallbackExecutorAdapter
  default:
    OPENHANDS_ENABLED=true    → OpenHandsExecutorAdapter
    ALLOW_FALLBACK_EXECUTOR=true → FallbackExecutorAdapter
    otherwise                 → fail clearly

Does NOT add Aider or SWE-agent adapters.
"""

from __future__ import annotations

import os
from typing import Any

from adapters.execution.base import ExecutionAdapter
from adapters.execution.fallback_adapter import FallbackExecutorAdapter
from adapters.execution.openhands_adapter import OpenHandsExecutorAdapter


class ExecutionRouter:
    """Routes action execution to the configured backend."""

    def __init__(
        self,
        executor_backend: str | None = None,
        openhands_enabled: bool | None = None,
        allow_fallback: bool | None = None,
    ):
        self._backend = executor_backend or os.environ.get("EXECUTOR_BACKEND", "")
        self._openhands_enabled = (
            openhands_enabled
            if openhands_enabled is not None
            else os.environ.get("OPENHANDS_ENABLED", "false").lower() == "true"
        )
        self._allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.environ.get("ALLOW_FALLBACK_EXECUTOR", "false").lower() == "true"
        )

        self._openhands: ExecutionAdapter | None = None
        self._fallback: ExecutionAdapter | None = None

    def _get_adapter(self) -> ExecutionAdapter:
        if self._backend == "openhands":
            if self._openhands is None:
                self._openhands = OpenHandsExecutorAdapter()
            return self._openhands

        if self._backend == "fallback":
            if self._fallback is None:
                self._fallback = FallbackExecutorAdapter()
            return self._fallback

        # Default resolution
        if self._openhands_enabled:
            if self._openhands is None:
                self._openhands = OpenHandsExecutorAdapter()
            return self._openhands

        if self._allow_fallback:
            if self._fallback is None:
                self._fallback = FallbackExecutorAdapter()
            return self._fallback

        raise RuntimeError(
            "No execution backend configured. Set EXECUTOR_BACKEND=openhands "
            "or EXECUTOR_BACKEND=fallback, or enable OPENHANDS_ENABLED=true "
            "or ALLOW_FALLBACK_EXECUTOR=true."
        )

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        adapter = self._get_adapter()
        return await adapter.execute_action(
            session_id, worktree_path, action_name, params, context
        )

    @property
    def backend_name(self) -> str:
        """Return the name of the active backend."""
        try:
            adapter = self._get_adapter()
            if isinstance(adapter, OpenHandsExecutorAdapter):
                return "openhands"
            if isinstance(adapter, FallbackExecutorAdapter):
                return "fallback"
            return "unknown"
        except RuntimeError:
            return "none"
