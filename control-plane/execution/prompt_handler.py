"""
Prompt handler — end-to-end orchestration for user prompts.

Flow:
  1. Receive prompt for a session
  2. Route via prompt_router (LLM or heuristic)
  3. Validate session state and runtime policy
  4. Call agent-core for advisory planning (optional)
  5. Execute via OpenHands runtime adapter
  6. Record events to live feed
  7. Return task handle with truthful state

This module ties together:
  - prompt_router.router (routing decisions)
  - agent_core_client.client (advisory planning)
  - executors.openhands_adapter (execution)
  - live_feed.events (event recording)
  - execution.runtime_validator (policy checks)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Dedicated thread pool for agent execution (avoids exhausting asyncio's default pool)
_agent_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("AGENT_POOL_SIZE", "8")),
    thread_name_prefix="agent",
)

def _sessions_dir() -> Path:
    return Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


SESSIONS_DIR = _sessions_dir()
OPENHANDS_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


class TaskState(str, Enum):
    """Truthful task execution states."""
    RECEIVED = "received"
    ROUTING = "routing"
    PLANNING = "planning"
    QUEUED = "queued"
    EXECUTOR_STARTING = "executor_starting"
    EXECUTOR_RUNNING = "executor_running"
    EDITING = "editing"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    COMMITTED = "committed"


@dataclass
class TaskHandle:
    """Returned to the caller after submitting a prompt."""
    task_id: str
    session_id: str
    state: TaskState
    message: str = ""
    routing_decision: str = ""
    plan_summary: str = ""
    error: str = ""
    events_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimePolicy:
    """Runtime policy checks before execution."""
    allowed_actions: list[str] = field(default_factory=lambda: [
        "grep", "read_file", "apply_patch", "run_tests",
        "summarize_diff", "commit",
    ])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "shutdown", "reboot", "mkfs",
    ])
    mutation_allowed: bool = True
    commit_requires_approval: bool = True
    push_requires_approval: bool = True
    deploy_requires_approval: bool = True
    secrets_require_approval: bool = True


def _emit_event(session_id: str, event_type: str, message: str = "", metadata: dict = None):
    """Append an event to the session's events.jsonl."""
    from live_feed.events import EventStore, EventType, SessionEvent
    store = EventStore(_sessions_dir())
    try:
        etype = EventType(event_type)
    except ValueError:
        etype = EventType.ACTION_PROGRESS
    event = SessionEvent(
        event_type=etype,
        session_id=session_id,
        data={"message": message, **(metadata or {})},
    )
    store.append(event)
    return event


def _check_runtime_policy(
    session_id: str,
    instruction: str,
    policy: RuntimePolicy,
) -> tuple[bool, str]:
    """Check runtime policy before execution.

    Returns (allowed, reason).
    """
    session_dir = _sessions_dir() / session_id
    if not session_dir.exists():
        return False, f"Session directory does not exist: {session_id}"

    lower = instruction.lower()
    for cmd in policy.blocked_commands:
        if cmd in lower:
            return False, f"Blocked command detected: {cmd}"

    mutation_keywords = ["delete", "remove", "drop", "destroy", "format"]
    if not policy.mutation_allowed:
        for kw in mutation_keywords:
            if kw in lower:
                return False, f"Mutation not allowed: {kw}"

    approval_keywords = {
        "commit": policy.commit_requires_approval,
        "push": policy.push_requires_approval,
        "deploy": policy.deploy_requires_approval,
    }
    for kw, requires in approval_keywords.items():
        if requires and kw in lower:
            return False, f"Action requires approval: {kw}"

    return True, ""


async def handle_prompt(
    session_id: str,
    instruction: str,
    model: str = "",
    use_agent_core: bool = True,
    policy: RuntimePolicy | None = None,
    execution_mode: str = "finite",
) -> TaskHandle:
    """End-to-end prompt handler.

    1. Emit prompt_received
    2. Route the prompt
    3. Check runtime policy
    4. Optionally call agent-core for advisory plan
    5. Execute via OpenHands
    6. Return task handle with truthful state
    """
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    policy = policy or RuntimePolicy()

    # 1. Record prompt received
    _emit_event(session_id, "user_prompt_received", instruction, {"task_id": task_id})

    # 2. Route the prompt
    try:
        from prompt_router.router import (
            RoutingDecision,
            RoutingInput,
            route_prompt_async,
        )
        routing_input = RoutingInput(
            session_id=session_id,
            prompt=instruction,
            current_plan_status="none",
        )
        routing_output = await route_prompt_async(routing_input)
        decision = routing_output.decision
        rationale = routing_output.rationale
    except Exception as e:
        logger.warning("Routing failed, defaulting to append_to_current: %s", e)
        decision = RoutingDecision.APPEND_TO_CURRENT
        rationale = f"[fallback] routing error: {e}"

    _emit_event(session_id, "routing_decision_made", rationale, {
        "decision": decision.value if hasattr(decision, "value") else str(decision),
        "task_id": task_id,
    })

    # Handle non-execution decisions
    if decision == RoutingDecision.INTERRUPT_CURRENT:
        _emit_event(session_id, "plan_cancelled", "User interrupted")
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.COMPLETED,
            routing_decision=decision.value,
            message="Session interrupted by user",
        )

    if decision == RoutingDecision.QUEUE:
        _emit_event(session_id, "action_progress", "Queued for later execution")
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.QUEUED,
            routing_decision=decision.value,
            message="Prompt queued — session is busy",
        )

    # 3. Check runtime policy
    allowed, reason = _check_runtime_policy(session_id, instruction, policy)
    if not allowed:
        _emit_event(session_id, "action_blocked", reason, {"task_id": task_id})
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.BLOCKED,
            routing_decision=decision.value,
            message=reason,
            error=reason,
        )

    # 4. Advisory planning from agent-core (best-effort)
    plan_summary = ""
    if use_agent_core:
        try:
            from agent_core_client.client import AgentCoreClient, PlanRequest
            client = AgentCoreClient()
            plan_request = PlanRequest(
                session_id=session_id,
                repo_id="",
                prompt=instruction,
                allowed_actions=policy.allowed_actions,
            )
            _emit_event(session_id, "plan_requested", "Requesting advisory plan from agent-core")
            plan_response = await client.plan(plan_request)
            await client.close()

            if plan_response.get("ok"):
                plan_obj = plan_response.get("plan", {})
                plan_steps = plan_obj.get("steps", [])
                plan_summary = str(plan_steps)[:200]
                # Include full plan data in event for dashboard display
                import json as _json
                plan_full = _json.dumps(plan_obj, indent=2, default=str)[:4000]
                _emit_event(session_id, "plan_generated", "Advisory plan received", {
                    "plan_mode": plan_obj.get("mode", "finite"),
                    "step_count": len(plan_steps),
                    "type": "plan_output",
                    "output": plan_full,
                })
            else:
                _emit_event(session_id, "plan_validation_failed",
                            plan_response.get("errors", ["unknown"])[0] if plan_response.get("errors") else "Plan generation failed")
        except Exception as e:
            logger.info("agent-core advisory planning unavailable: %s", e)
            # Non-fatal: proceed without plan

    # 5. Execute via OpenHands
    _emit_event(session_id, "action_started", "Starting OpenHands executor", {"task_id": task_id})

    try:
        result = await _execute_via_openhands(session_id, instruction, task_id, model, execution_mode)
    except Exception as e:
        error_msg = f"Execution failed: {e}"
        _emit_event(session_id, "action_failed", error_msg, {"task_id": task_id})
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.FAILED,
            routing_decision=decision.value,
            plan_summary=plan_summary,
            message=error_msg,
            error=str(e),
            events_path=str(_sessions_dir() / session_id / "events" / "events.jsonl"),
        )

    # 6. Determine final state
    final_state = TaskState.COMPLETED
    if result.get("status") == "blocked":
        final_state = TaskState.BLOCKED
    elif result.get("status") == "failed":
        final_state = TaskState.FAILED
    elif result.get("status") == "needs_review":
        final_state = TaskState.NEEDS_REVIEW

    event_type = "action_completed" if final_state == TaskState.COMPLETED else "action_failed"
    _emit_event(session_id, event_type, result.get("summary", ""), {
        "task_id": task_id,
        "files_edited": result.get("files_edited", []),
        "executor": "openhands",
    })

    return TaskHandle(
        task_id=task_id,
        session_id=session_id,
        state=final_state,
        routing_decision=decision.value,
        plan_summary=plan_summary,
        message=result.get("summary", "Execution complete"),
        events_path=str(_sessions_dir() / session_id / "events" / "events.jsonl"),
        metadata={
            "files_edited": result.get("files_edited", []),
            "executor": "openhands",
            "duration_seconds": result.get("duration_seconds", 0),
        },
    )


async def _execute_via_openhands(
    session_id: str,
    instruction: str,
    task_id: str,
    model: str = "",
    execution_mode: str = "finite",
) -> dict[str, Any]:
    """Execute instruction via the OpenHands local executor adapter.

    Uses vendored OpenHands SDK concepts with LLM tool-calling loop.
    Executes directly on host filesystem — no Docker runtime needed.
    """
    from executors.openhands_adapter import OpenHandsExecutorAdapter

    session_dir = _sessions_dir() / session_id
    meta_path = session_dir / "meta.json"

    import json as _json
    worktree_path = ""
    branch = ""
    if meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text())
            worktree_path = meta.get("repo_path", "") or meta.get("worktree_path", "")
            branch = meta.get("branch", "")
        except Exception:
            pass

    if not worktree_path or not Path(worktree_path).exists():
        # Fall back to DEFAULT_REPO_PATH env var, then error
        worktree_path = os.environ.get("DEFAULT_REPO_PATH", "")
        if not worktree_path or not Path(worktree_path).exists():
            return {
                "status": "failed",
                "summary": "No valid workspace found for session. Set DEFAULT_REPO_PATH or create session with a repo.",
                "files_edited": [],
                "duration_seconds": 0,
            }

    adapter = OpenHandsExecutorAdapter()

    if not adapter.is_available():
        return {
            "status": "blocked",
            "summary": "Execution backend (LiteLLM) is unavailable",
            "files_edited": [],
            "duration_seconds": 0,
        }

    from executors.base import TaskPacket
    packet = TaskPacket(
        task_id=task_id,
        session_id=session_id,
        instruction=instruction,
        worktree_path=worktree_path,
        branch=branch or "main",
        model=model or os.environ.get("DEFAULT_MODEL", "deepseek-chat"),
        execution_mode=execution_mode,
    )

    start = time.time()
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_agent_executor, adapter.run_task, session_id, packet)
        duration = time.time() - start
        # Get raw output from events (last executor_finished event)
        raw_output = ""
        events_file = _sessions_dir() / session_id / "events" / "events.jsonl"
        if events_file.exists():
            import json as _j2
            for line in reversed(events_file.read_text().strip().split("\n")):
                try:
                    ev = _j2.loads(line)
                    if ev.get("event_type") == "action_progress" and "Tool:" in ev.get("data", {}).get("message", ""):
                        # Get the args summary which has the command
                        pass
                except Exception:
                    pass

        return {
            "status": result.status,
            "summary": result.summary,
            "files_edited": result.files_edited,
            "duration_seconds": duration,
            "tests_passed": result.tests_passed,
            "tests_failed": result.tests_failed,
            "commands_run": result.commands_run,
        }
    except Exception as e:
        duration = time.time() - start
        error_str = str(e)
        return {
            "status": "failed",
            "summary": f"Execution error: {error_str[:200]}",
            "files_edited": [],
            "duration_seconds": duration,
        }


def get_task_state(session_id: str) -> dict[str, Any]:
    """Get current truthful state for a session by reading events."""
    events_path = _sessions_dir() / session_id / "events" / "events.jsonl"
    if not events_path.exists():
        return {"state": "unknown", "events": []}

    events = []
    for line in events_path.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(__import__("json").loads(line))
            except Exception:
                continue

    if not events:
        return {"state": "session_created", "events": []}

    last = events[-1]
    event_type = last.get("event_type", "")

    state_map = {
        "user_prompt_received": "prompt_received",
        "routing_decision_made": "routing",
        "plan_requested": "planning",
        "plan_generated": "planning",
        "plan_validation_failed": "failed",
        "plan_started": "executor_starting",
        "action_started": "executor_running",
        "action_progress": "editing",
        "action_blocked": "blocked",
        "action_completed": "completed",
        "action_failed": "failed",
        "plan_paused": "blocked",
        "plan_resumed": "executor_running",
        "plan_cancelled": "completed",
        "plan_completed": "completed",
        "commit_created": "committed",
    }

    return {
        "state": state_map.get(event_type, "unknown"),
        "last_event": event_type,
        "total_events": len(events),
        "events": events[-10:],  # Last 10 events
    }
