"""
InProcessWorkflowAdapter — dev/test fallback workflow runner.

Runs the workflow coroutine directly via asyncio.create_task.
NOT durable. NOT production. Use only when:
  WORKFLOW_BACKEND=inprocess
or explicit test configuration is active.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Coroutine

from adapters.workflow.base import WorkflowAdapter


class InProcessWorkflowAdapter(WorkflowAdapter):
    """Non-durable workflow execution for dev/test.

    Runs the execute_agent_plan coroutine directly in the event loop.
    Control intents are tracked in-memory.
    """

    def __init__(self):
        self._control_intents: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._workflow_fn: Callable[..., Coroutine] | None = None

    def set_workflow_fn(
        self, fn: Callable[..., Coroutine]
    ) -> None:
        """Register the workflow coroutine to run when start_plan is called."""
        self._workflow_fn = fn

    async def start_plan(
        self, session_id: str, plan: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        run_id = f"inprocess-{uuid.uuid4().hex[:8]}"
        self._control_intents.pop(session_id, None)

        if self._workflow_fn is not None:
            task = asyncio.create_task(
                self._workflow_fn(session_id, plan, context)
            )
            self._tasks[session_id] = task

        return {
            "started": True,
            "backend": "inprocess",
            "session_id": session_id,
            "workflow_run_id": run_id,
        }

    async def pause(self, session_id: str) -> dict[str, Any]:
        self._control_intents[session_id] = "pause"
        return {
            "accepted": True,
            "backend": "inprocess",
            "session_id": session_id,
            "mechanism": "session_state_control_intent",
        }

    async def resume(self, session_id: str) -> dict[str, Any]:
        self._control_intents.pop(session_id, None)
        return {
            "accepted": True,
            "backend": "inprocess",
            "session_id": session_id,
            "mechanism": "session_state_control_intent",
        }

    async def cancel(self, session_id: str) -> dict[str, Any]:
        self._control_intents[session_id] = "cancel"
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
        return {
            "accepted": True,
            "backend": "inprocess",
            "session_id": session_id,
            "mechanism": "task_cancel",
        }

    async def status(self, session_id: str) -> dict[str, Any]:
        intent = self._control_intents.get(session_id, "running")
        task = self._tasks.get(session_id)
        task_status = "not_started"
        if task is not None:
            if task.done():
                task_status = "completed"
            elif task.cancelled():
                task_status = "cancelled"
            else:
                task_status = "running"
        return {
            "backend": "inprocess",
            "session_id": session_id,
            "control_intent": intent,
            "task_status": task_status,
        }

    def get_control_intent(self, session_id: str) -> str:
        """Check if there is a pending control intent for a session."""
        return self._control_intents.get(session_id, "")
