"""
execute_agent_plan — the core workflow that runs an advisory plan.

For each plan step:
  1. Reload session state
  2. Stop if cancelled
  3. Pause/return if paused
  4. Emit ACTION_STARTED
  5. Runtime validate step
  6. If blocked: emit ACTION_BLOCKED, record outcome, decide continue/stop
  7. Choose execution path:
       atomic -> ExecutionRouter -> AgenticExecutor/DeterministicExecutor
       composite -> CompositeActionRouter -> LangGraph -> ExecutionRouter
  8. Execute step
  9. Emit ACTION_COMPLETED or ACTION_FAILED
  10. Record outcome to agent-core (POST /actions/outcome)
  11. If commit succeeded, emit COMMIT_CREATED

Plan modes:
  finite: run steps once
  loop: run one iteration, emit PLAN_COMPLETED with needs_refresh=true
  open_ended: run one iteration, emit PLAN_COMPLETED with needs_refresh=true

Does not implement uncontrolled infinite loops.
"""

from __future__ import annotations

import time
from typing import Any

from adapters.composite_action.base import is_composite_action
from adapters.composite_action.router import CompositeActionRouter
from adapters.execution.router import ExecutionRouter
from agent_core_client.client import AgentCoreClient, OutcomeRecord
from execution.redaction import redact_output, redact_value
from execution.results import ExecutionResult
from execution.runtime_validator import RuntimeValidator
from live_feed.events import EventStore, EventType, create_event
from sessions.models import SessionStatus, SessionStore

# Platform-native actions that executors should not claim credit for
_PLATFORM_ONLY_EVENT_TYPES = {
    "pr_created", "pr_merged", "ci_passed",
    "service_deployed", "validation_passed",
}


class PlanExecutor:
    """Executes an advisory plan step-by-step.

    This is the core workflow logic. In production, Hatchet invokes this.
    In dev/test, InProcessWorkflowAdapter runs it as a coroutine.
    """

    def __init__(
        self,
        session_store: SessionStore,
        event_store: EventStore,
        execution_router: ExecutionRouter,
        composite_router: CompositeActionRouter,
        runtime_validator: RuntimeValidator,
        agent_core_client: AgentCoreClient | None = None,
        worktree_base: str = "/opt/workstation/repos",
    ):
        self.session_store = session_store
        self.event_store = event_store
        self.execution_router = execution_router
        self.composite_router = composite_router
        self.runtime_validator = runtime_validator
        self.agent_core_client = agent_core_client
        self.worktree_base = worktree_base

    async def execute(
        self,
        session_id: str,
        plan: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a plan for a session.

        Args:
            session_id: The session executing this plan.
            plan: Advisory plan from agent-core (goal, mode, steps).
            context: Execution context (repo_id, worktree_id, allowed_actions).

        Returns:
            {completed, steps_executed, steps_failed, needs_refresh, results}
        """
        steps = plan.get("steps", [])
        mode = plan.get("mode", "finite")
        goal = plan.get("goal", "")
        worktree_id = context.get("worktree_id", "")
        worktree_path = f"{self.worktree_base}/{worktree_id}" if worktree_id else ""
        executor_context = self._executor_context(context)

        results: list[dict[str, Any]] = []
        steps_executed = 0
        steps_failed = 0

        # Check current status before overriding
        session = self.session_store.get(session_id)
        if session and session.status not in (SessionStatus.CANCELLED, SessionStatus.PAUSED):
            self.session_store.update_status(session_id, SessionStatus.EDITING)

        for i, step in enumerate(steps):
            action_name = step.get("action_name", "")
            params = step.get("params", {})
            rationale = step.get("rationale", "")

            # 1. Reload session to check current state
            session = self.session_store.get(session_id)
            if session is None:
                break

            # 2. Stop if cancelled
            if session.status == SessionStatus.CANCELLED:
                self.event_store.append(
                    create_event(
                        EventType.PLAN_CANCELLED, session_id,
                        reason="session_cancelled",
                    )
                )
                break

            # 3. Pause if paused
            if session.status == SessionStatus.PAUSED:
                self.event_store.append(
                    create_event(
                        EventType.PLAN_PAUSED, session_id,
                        reason="session_paused",
                        step_index=i,
                    )
                )
                break

            # 4. Emit ACTION_STARTED
            self.event_store.append(
                create_event(
                    EventType.ACTION_STARTED, session_id,
                    action_name=action_name,
                    params=params,
                    step_index=i,
                    rationale=rationale,
                )
            )

            # 5. Runtime validate
            validation = self.runtime_validator.validate(
                session_id, action_name, params
            )

            if not validation.allowed:
                # 6. Blocked
                self.event_store.append(
                    create_event(
                        EventType.ACTION_BLOCKED, session_id,
                        action_name=action_name,
                        reason=validation.reason,
                        step_index=i,
                    )
                )
                await self._record_outcome(
                    session_id, action_name, params,
                    status="blocked", error=validation.reason,
                    duration_ms=0, rationale=rationale,
                )
                steps_failed += 1
                results.append({
                    "step_index": i,
                    "action_name": action_name,
                    "status": "blocked",
                    "error": validation.reason,
                })
                continue

            # Use normalized params
            params = validation.normalized_params or params

            # 7-8. Execute
            start_ms = int(time.time() * 1000)
            if is_composite_action(action_name):
                exec_result = await self.composite_router.execute_composite_action(
                    session_id, worktree_path, action_name, params,
                    executor_context,
                )
            else:
                exec_result = await self.execution_router.execute_action(
                    session_id, worktree_path, action_name, params,
                    executor_context,
                )
            duration_ms = int(time.time() * 1000) - start_ms

            # Normalize: ExecutionResult (dataclass) or dict (legacy)
            if isinstance(exec_result, ExecutionResult):
                status = exec_result.status
                backend = exec_result.backend
                error = exec_result.error
                output = exec_result.output
                files_touched = exec_result.files_touched
                executor_events = exec_result.events
            else:
                status = exec_result.get("status", "failed")
                backend = exec_result.get("backend", "")
                error = exec_result.get("error", "")
                output = exec_result.get("output", {})
                files_touched = exec_result.get("files_touched", [])
                executor_events = []

            steps_executed += 1

            # Append executor events to EventStore (filtered)
            for evt in executor_events:
                evt_type = getattr(evt, "event_type", "") if hasattr(evt, "event_type") else ""
                if evt_type in _PLATFORM_ONLY_EVENT_TYPES:
                    continue
                self.event_store.append(
                    create_event(
                        EventType.ACTION_PROGRESS, session_id,
                        action_name=action_name,
                        step_index=i,
                        executor_event=redact_value(evt.to_dict() if hasattr(evt, "to_dict") else {}),
                    )
                )

            # 9. Emit ACTION_COMPLETED or ACTION_FAILED
            if status == "succeeded":
                self.event_store.append(
                    create_event(
                        EventType.ACTION_COMPLETED, session_id,
                        action_name=action_name,
                        status=status,
                        backend=backend,
                        duration_ms=duration_ms,
                        step_index=i,
                        files_touched=files_touched,
                    )
                )
            else:
                self.event_store.append(
                    create_event(
                        EventType.ACTION_FAILED, session_id,
                        action_name=action_name,
                        status=status,
                        error=error,
                        backend=backend,
                        duration_ms=duration_ms,
                        step_index=i,
                    )
                )
                steps_failed += 1

            # 10. Record outcome to agent-core
            await self._record_outcome(
                session_id, action_name, params,
                status=status,
                output=redact_value(output),
                error=redact_output(error),
                duration_ms=duration_ms,
                rationale=rationale,
                files_touched=files_touched,
                executor=backend,
            )

            # 11. If commit succeeded, emit COMMIT_CREATED
            if action_name == "commit" and status == "succeeded":
                commit_hash = ""
                if isinstance(output, dict):
                    commit_hash = output.get("commit_hash", "")
                if commit_hash:
                    self.event_store.append(
                        create_event(
                            EventType.COMMIT_CREATED, session_id,
                            commit_hash=commit_hash,
                            message=params.get("message", ""),
                            trigger="plan_execution",
                        )
                    )

            results.append({
                "step_index": i,
                "action_name": action_name,
                "status": status,
                "backend": backend,
                "duration_ms": duration_ms,
                "files_touched": files_touched,
            })

        # Emit PLAN_COMPLETED
        needs_refresh = mode in ("loop", "open_ended")
        self.event_store.append(
            create_event(
                EventType.PLAN_COMPLETED, session_id,
                goal=goal,
                mode=mode,
                steps_executed=steps_executed,
                steps_failed=steps_failed,
                needs_refresh=needs_refresh,
            )
        )

        # Update session status
        if steps_failed > 0 and steps_executed == steps_failed:
            self.session_store.update_status(session_id, SessionStatus.FAILED)
        else:
            self.session_store.update_status(session_id, SessionStatus.COMPLETED)

        return {
            "completed": True,
            "steps_executed": steps_executed,
            "steps_failed": steps_failed,
            "needs_refresh": needs_refresh,
            "results": results,
        }

    def _executor_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Normalize workflow context before it reaches execution adapters."""

        executor_context = dict(context)
        if not executor_context.get("plan_context") and executor_context.get("ambient_prompt_context"):
            executor_context["plan_context"] = executor_context["ambient_prompt_context"]
        return executor_context

    async def _record_outcome(
        self,
        session_id: str,
        action_name: str,
        params: dict[str, Any],
        status: str = "",
        output: dict[str, Any] | None = None,
        error: str = "",
        duration_ms: int = 0,
        rationale: str = "",
        files_touched: list[str] | None = None,
        executor: str = "",
    ) -> None:
        """Record an action outcome to agent-core."""
        if self.agent_core_client is None:
            return
        try:
            outcome = OutcomeRecord(
                session_id=session_id,
                action_name=action_name,
                params=params,
                status=status,
                output=output or {},
                duration_ms=duration_ms,
                executor=executor or "jubilant-goggles",
                rationale=rationale,
                error=error,
                files_touched=files_touched or [],
            )
            await self.agent_core_client.record_outcome(outcome)
        except Exception:
            pass  # Best-effort recording; do not block execution
