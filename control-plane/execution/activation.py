"""Shared execution activation scaffold.

Intent
------
This module is the future extraction point for the execution-start logic that is
currently private to ``SessionController._request_next_action_and_start_workflow``.
The service exists so all entry points can share one path:

    ready work session
    -> request agent-core recommend-next
    -> validate the action contract
    -> validate platform/runtime permissions
    -> start the workflow adapter
    -> emit truthful events

Boundaries
----------
* agent-core remains advisory: it recommends and validates action contract shape.
* jubilant-goggles remains authoritative: it validates repo/worktree/runtime safety
  and starts or refuses execution.
* No caller may mark ``auto_started`` true unless a workflow adapter actually
  accepted a plan.

Current state
-------------
This is intentional scaffolding. The default service records whether work is
blocked, ready but not started, or started by an injected callback. Production
wiring should inject the extracted workflow-start function after it is moved out
of ``SessionController``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class ExecutionActivationSource(str, Enum):
    """Where a request to start execution came from."""

    API_V2_SESSION_PROMPT = "api_v2_session_prompt"
    SESSION_GRAPH_CHAT = "session_graph_chat"
    REPO_ATTACHMENT_TRIGGER = "repo_attachment_trigger"
    MANUAL_START = "manual_start"


class ExecutionActivationStatus(str, Enum):
    """Truthful activation states.

    ``STARTED`` is reserved for the case where workflow start has actually
    succeeded. Everything else is non-executing state.
    """

    BLOCKED_NEEDS_REPO = "blocked_needs_repo"
    READY_NOT_STARTED = "ready_not_started"
    STARTED = "started"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class ExecutionActivationRequest:
    """Canonical request to activate execution for one work unit.

    Keep this data independent of the session graph model so the same request can
    be created from classic sessions, graph work sessions, repo-attachment
    triggers, or manual start buttons.
    """

    session_id: str
    prompt: str
    source: ExecutionActivationSource
    mode_preference: str = "finite"
    parent_session_id: str = ""
    root_session_id: str = ""
    repo_id: str = ""
    repo_context_id: str = ""
    worktree_id: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_repo_context(self) -> bool:
        return bool(self.repo_id or self.repo_context_id or self.worktree_id)


@dataclass(frozen=True)
class ExecutionActivationResult:
    """Result returned to graph/API callers.

    ``auto_started`` is derived from status so a scaffolded or failed activation
    cannot accidentally claim work started.
    """

    status: ExecutionActivationStatus
    message: str
    activation_id: str = ""
    plan: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def auto_started(self) -> bool:
        return self.status == ExecutionActivationStatus.STARTED

    def to_response_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status.value,
            "message": self.message,
            "auto_started": self.auto_started,
        }
        if self.activation_id:
            payload["activation_id"] = self.activation_id
        if self.plan is not None:
            payload["plan"] = self.plan
        if self.workflow is not None:
            payload["workflow"] = self.workflow
        if self.error:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


StartWorkflowCallback = Callable[[ExecutionActivationRequest], Awaitable[dict[str, Any]]]


class ExecutionActivationService:
    """Shared execution activation boundary.

    The eventual implementation should move the recommend-next and workflow-start
    code from ``SessionController`` into this service. Until then, callers can use
    it to record consistent non-starting state and to prevent fake success.
    """

    def __init__(self, start_workflow: StartWorkflowCallback | None = None):
        self.start_workflow = start_workflow

    async def activate(self, request: ExecutionActivationRequest) -> ExecutionActivationResult:
        """Activate execution if possible.

        This method intentionally returns non-starting states unless a workflow
        callback is injected and succeeds.
        """

        if not request.has_repo_context:
            return ExecutionActivationResult(
                status=ExecutionActivationStatus.BLOCKED_NEEDS_REPO,
                message="Repository context is required before execution can start.",
                metadata={"source": request.source.value},
            )

        if self.start_workflow is None:
            return ExecutionActivationResult(
                status=ExecutionActivationStatus.READY_NOT_STARTED,
                message="Execution activation is scaffolded; workflow start is not wired for this entry point yet.",
                metadata={"source": request.source.value, "requires_workflow_callback": True},
            )

        try:
            workflow_result = await self.start_workflow(request)
        except Exception as exc:  # pragma: no cover - implementation callback owns concrete failures.
            return ExecutionActivationResult(
                status=ExecutionActivationStatus.FAILED,
                message="Execution activation failed before workflow start could be confirmed.",
                error=str(exc),
                metadata={"source": request.source.value},
            )

        return ExecutionActivationResult(
            status=ExecutionActivationStatus.STARTED,
            message="Workflow start accepted by execution adapter.",
            plan=workflow_result.get("plan") if isinstance(workflow_result.get("plan"), dict) else None,
            workflow=workflow_result.get("workflow") if isinstance(workflow_result.get("workflow"), dict) else workflow_result,
            metadata={"source": request.source.value},
        )
