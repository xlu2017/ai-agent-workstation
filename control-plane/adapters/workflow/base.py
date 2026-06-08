"""
WorkflowAdapter interface — durable workflow execution abstraction.

Workflow adapters manage plan lifecycle:
  start_plan  — begin executing an agent-core advisory plan
  pause       — pause the running workflow
  resume      — resume a paused workflow
  cancel      — cancel the running workflow
  status      — get current workflow status

Implementations:
  HatchetWorkflowAdapter  — production durable execution via Hatchet
  InProcessWorkflowAdapter — dev/test only, runs coroutine directly
"""

from __future__ import annotations

import abc
from typing import Any


class WorkflowAdapter(abc.ABC):
    """Abstract base for durable workflow execution."""

    @abc.abstractmethod
    async def start_plan(
        self, session_id: str, plan: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Start executing an advisory plan.

        Args:
            session_id: Session that owns the plan.
            plan: Advisory plan from agent-core (goal, mode, steps).
            context: Execution context (repo_id, worktree_id, allowed_actions).

        Returns:
            {started, backend, session_id, workflow_run_id?, ...}
        """
        ...

    @abc.abstractmethod
    async def pause(self, session_id: str) -> dict[str, Any]:
        """Pause the running workflow for a session."""
        ...

    @abc.abstractmethod
    async def resume(self, session_id: str) -> dict[str, Any]:
        """Resume a paused workflow."""
        ...

    @abc.abstractmethod
    async def cancel(self, session_id: str) -> dict[str, Any]:
        """Cancel the running workflow."""
        ...

    @abc.abstractmethod
    async def status(self, session_id: str) -> dict[str, Any]:
        """Get current workflow status."""
        ...
