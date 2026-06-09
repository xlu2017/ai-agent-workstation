"""
Prompt handler — end-to-end orchestration for user prompts.

Flow:
  1. Receive prompt for a session
  2. Route via prompt_router (LLM or heuristic)
  3. Validate session state and runtime policy
  4. Call agent-core for advisory planning (optional)
  5. Execute via agentic executor
  6. Record events to live feed
  7. Return task handle with truthful state

This module ties together:
  - prompt_router.router (routing decisions)
  - agent_core_client.client (advisory planning)
  - execution.agentic_executor (execution)
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
LITELLM_PROXY_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


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
    commit_requires_approval: bool = False
    push_requires_approval: bool = False
    deploy_requires_approval: bool = False
    secrets_require_approval: bool = False


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
    5. Execute via agentic executor
    6. Return task handle with truthful state
    """
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    policy = policy or RuntimePolicy()

    # 1. Record prompt received
    _emit_event(session_id, "user_prompt_received", instruction, {"task_id": task_id})

    # 2. Route the prompt
    task_class = ""
    direct_action = ""
    classification_confidence = 0.0
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
        task_class = getattr(routing_output, "task_class", "")
        direct_action = getattr(routing_output, "direct_action", "")
        classification_confidence = getattr(routing_output, "classification_confidence", 0.0)
    except Exception as e:
        logger.warning("Routing failed, defaulting to append_to_current: %s", e)
        # Use string fallback in case the import itself failed
        decision = "append_to_current"
        rationale = f"[fallback] routing error: {e}"

    # Build a clean user-facing status message instead of raw LLM rationale
    _decision_labels = {
        "append_to_current": "Continuing with your request.",
        "modify_current_plan": "Updating the current plan with your changes.",
        "interrupt_current": "Stopping the current task.",
        "spawn_child_session": "Starting a related task in a new session.",
        "spawn_new_session": "Starting a new session for this task.",
        "queue": "Queued — will start once the current operation finishes.",
    }
    decision_val = decision.value if hasattr(decision, "value") else str(decision)
    display_message = _decision_labels.get(decision_val, "Processing your request.")

    routing_metadata: dict[str, Any] = {
        "decision": decision_val,
        "task_id": task_id,
        "rationale": rationale,
    }
    if task_class:
        routing_metadata["task_class"] = task_class
    if direct_action:
        routing_metadata["direct_action"] = direct_action
    if classification_confidence > 0:
        routing_metadata["classification_confidence"] = classification_confidence
    _emit_event(session_id, "routing_decision_made", display_message, routing_metadata)

    # Handle non-execution decisions
    if decision_val == "interrupt_current":
        _emit_event(session_id, "plan_cancelled", "User interrupted")
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.COMPLETED,
            routing_decision=decision_val,
            message="Session interrupted by user",
        )

    if decision_val == "queue":
        _emit_event(session_id, "action_progress", "Queued for later execution")
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.QUEUED,
            routing_decision=decision_val,
            message="Prompt queued — session is busy",
        )

    # 2a. Emit initial status message and task decomposition
    try:
        from worklog.transcript import generate_status_message, generate_task_decomposition
        status_msg = generate_status_message(instruction, task_class, direct_action)
        _emit_event(session_id, "task_started", status_msg, {
            "task_id": task_id,
            "task_class": task_class,
            "instruction_preview": instruction[:200],
        })

        # Emit task decomposition for code-fix / implementation prompts
        if task_class != "desktop_control" and not direct_action:
            tasks = generate_task_decomposition(instruction, task_class)
            if tasks:
                _emit_event(session_id, "task_created", f"Created {len(tasks)} Tasks", {
                    "task_id": task_id,
                    "count": len(tasks),
                    "tasks": [t["title"] for t in tasks],
                })
    except Exception as e:
        logger.debug("Status message generation failed (non-fatal): %s", e)

    # 2b. Mutation guard: desktop_control tasks must not modify files or commit
    if task_class == "desktop_control":
        policy.mutation_allowed = False
        policy.commit_requires_approval = True
        policy.push_requires_approval = True
        logger.info(
            "Mutation guard active for desktop_control task (action=%s, confidence=%.2f)",
            direct_action,
            classification_confidence,
        )

    # 2c. Direct action fast path: execute deterministic desktop actions without LLM
    if direct_action and task_class == "desktop_control" and classification_confidence >= 0.65:
        try:
            result = await _execute_direct_action(session_id, task_id, direct_action, instruction)
            return result
        except Exception as e:
            logger.warning("Direct action %s failed, falling through to agentic: %s", direct_action, e)
            _emit_event(session_id, "action_failed", f"Direct action failed: {e}", {
                "task_id": task_id, "direct_action": direct_action,
            })
            # Fall through to agentic executor as fallback

    # 3. Check runtime policy
    allowed, reason = _check_runtime_policy(session_id, instruction, policy)
    if not allowed:
        _emit_event(session_id, "action_blocked", reason, {"task_id": task_id})
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.BLOCKED,
            routing_decision=decision_val,
            message=reason,
            error=reason,
        )

    # 4. Advisory planning from agent-core (best-effort)
    plan_summary = ""
    if use_agent_core:
        try:
            from agent_core_client.client import AgentCoreClient, PlanRequest
            client = AgentCoreClient()
            max_iter = int(os.environ.get("AGENTIC_EXECUTOR_MAX_ITERATIONS", "50"))
            plan_request = PlanRequest(
                session_id=session_id,
                repo_id="",
                prompt=instruction,
                allowed_actions=policy.allowed_actions,
                max_iterations=max_iter,
            )
            _emit_event(session_id, "plan_requested", "Requesting advisory plan from agent-core", metadata={
                "prompt": instruction,
            })
            plan_response = await client.plan(plan_request)
            await client.close()

            # Capture the full messages sent to the DeepSeek API
            import json as _json
            llm_messages = plan_response.get("llm_messages", [])
            llm_prompt_full = _json.dumps(llm_messages, indent=2, default=str) if llm_messages else ""

            if plan_response.get("ok"):
                plan_obj = plan_response.get("plan", {})
                plan_steps = plan_obj.get("steps", [])
                plan_summary = str(plan_steps)[:200]
                # Include full plan data and LLM messages in event for dashboard display
                plan_full = _json.dumps(plan_obj, indent=2, default=str)[:4000]
                _emit_event(session_id, "plan_generated", "Advisory plan received", {
                    "plan_mode": plan_obj.get("mode", "finite"),
                    "step_count": len(plan_steps),
                    "type": "plan_output",
                    "output": plan_full,
                    "llm_prompt": llm_prompt_full,
                })
            else:
                _emit_event(session_id, "plan_validation_failed",
                            plan_response.get("errors", ["unknown"])[0] if plan_response.get("errors") else "Plan generation failed")
        except Exception as e:
            logger.info("agent-core advisory planning unavailable: %s", e)
            # Non-fatal: proceed without plan

    # 5. Execute via agentic executor
    _emit_event(session_id, "action_started", "Starting executor", {"task_id": task_id})

    try:
        result = await _execute_via_agentic(session_id, instruction, task_id, model, execution_mode)
    except Exception as e:
        error_msg = f"Execution failed: {e}"
        _emit_event(session_id, "action_failed", error_msg, {"task_id": task_id})
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.FAILED,
            routing_decision=decision_val,
            plan_summary=plan_summary,
            message=error_msg,
            error=str(e),
            events_path=str(_sessions_dir() / session_id / "events" / "events.jsonl"),
        )

    # 6. Determine final state
    final_state = TaskState.COMPLETED
    result_status = result.get("status", "completed")
    if result_status == "blocked":
        final_state = TaskState.BLOCKED
    elif result_status == "failed":
        final_state = TaskState.FAILED
    elif result_status == "needs_review":
        final_state = TaskState.NEEDS_REVIEW
    elif result_status == "cancelled":
        _emit_event(session_id, "task_cancelled", "Stopped by user", {
            "task_id": task_id,
            "reason": "user_interrupt",
        })
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            state=TaskState.COMPLETED,
            routing_decision=decision_val,
            plan_summary=plan_summary,
            message="Stopped by user",
            events_path=str(_sessions_dir() / session_id / "events" / "events.jsonl"),
        )

    # Emit diff_summarized if files were edited
    files_edited = result.get("files_edited", [])
    if files_edited:
        additions = result.get("additions", 0)
        deletions = result.get("deletions", 0)
        _emit_event(session_id, "diff_summarized", f"+{additions} -{deletions}", {
            "task_id": task_id,
            "additions": additions,
            "deletions": deletions,
            "files": files_edited,
        })

    # Emit validation_completed with truthful status
    tests_passed = result.get("tests_passed", 0)
    tests_failed = result.get("tests_failed", 0)
    validation_status = "not_run"
    if tests_passed > 0 or tests_failed > 0:
        if tests_failed > 0 and tests_passed > 0:
            validation_status = "partial"
        elif tests_failed > 0:
            validation_status = "failed"
        else:
            validation_status = "passed"
        _emit_event(session_id, "validation_completed", f"Validation: {validation_status}", {
            "task_id": task_id,
            "status": validation_status,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
        })

    # Emit action/task completion
    event_type = "action_completed" if final_state == TaskState.COMPLETED else "action_failed"
    _emit_event(session_id, event_type, result.get("summary", ""), {
        "task_id": task_id,
        "files_edited": files_edited,
        "executor": "agentic",
    })

    # Emit task_completed for transcript aggregation
    _emit_event(session_id, "task_completed", result.get("summary", "Execution complete"), {
        "task_id": task_id,
        "status": result_status,
        "files_edited": files_edited,
        "validation": validation_status,
    })

    return TaskHandle(
        task_id=task_id,
        session_id=session_id,
        state=final_state,
        routing_decision=decision_val,
        plan_summary=plan_summary,
        message=result.get("summary", "Execution complete"),
        events_path=str(_sessions_dir() / session_id / "events" / "events.jsonl"),
        metadata={
            "files_edited": result.get("files_edited", []),
            "executor": "agentic",
            "duration_seconds": result.get("duration_seconds", 0),
        },
    )


def _auto_provision_workspace(session_id: str, session_dir: Path) -> tuple[str, str]:
    """Auto-provision a workspace when session.json is missing or worktree is gone.

    Tries to create a worktree from DEFAULT_REPO_PATH. If that's not set,
    scans REPOS_DIR for any available git repo. Writes session.json so
    subsequent requests don't need to re-provision.

    Returns (worktree_path, branch) or ("", "") if recovery failed.
    """
    import json as _json
    import subprocess

    repos_dir = Path(os.environ.get("REPOS_DIR", "/opt/workstation/repos"))
    default_repo = os.environ.get("DEFAULT_REPO_PATH", "")

    # Find a usable repo
    repo_path = ""
    if default_repo and Path(default_repo).exists() and (Path(default_repo) / ".git").exists():
        repo_path = default_repo
    else:
        # Scan repos dir for any git repo (prefer agent-core or jubilant-goggles)
        if repos_dir.exists():
            preferred = ["jubilant-goggles", "agent-core"]
            for name in preferred:
                candidate = repos_dir / name
                if candidate.exists() and (candidate / ".git").exists():
                    repo_path = str(candidate)
                    break
            if not repo_path:
                for child in sorted(repos_dir.iterdir()):
                    if child.is_dir() and (child / ".git").exists() and not child.name.startswith("worktree-"):
                        repo_path = str(child)
                        break

    if not repo_path:
        logger.warning("Auto-provision failed for %s: no git repo found", session_id)
        return ("", "")

    branch = f"{session_id}-branch"
    worktree_path = str(repos_dir / f"worktree-{session_id}")

    # Create worktree if it doesn't exist
    if not Path(worktree_path).exists():
        result = subprocess.run(
            ["git", "worktree", "add", worktree_path, "-b", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Branch might already exist — try without -b
            result = subprocess.run(
                ["git", "worktree", "add", worktree_path, branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Last resort: use HEAD directly
                result = subprocess.run(
                    ["git", "worktree", "add", "--detach", worktree_path],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "Auto-provision worktree failed for %s: %s",
                        session_id, result.stderr,
                    )
                    # Fall back to using the repo directly
                    worktree_path = repo_path
    else:
        # Worktree dir exists but session.json was missing — just wire it up
        pass

    # Ensure session dir structure exists
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "context").mkdir(exist_ok=True)
    (session_dir / "events").mkdir(exist_ok=True)

    # Write session.json for future requests
    from datetime import datetime, timezone
    meta = {
        "id": session_id,
        "repo_path": repo_path,
        "worktree_path": worktree_path,
        "branch": branch,
        "port_range": "",
        "browser_profile": session_id,
        "tmux_session": f"agent-{session_id}",
        "status": "active",
        "task": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auto_provisioned": True,
    }
    with open(session_dir / "session.json", "w") as f:
        _json.dump(meta, f, indent=2)

    logger.info(
        "Auto-provisioned workspace for session %s: repo=%s worktree=%s",
        session_id, repo_path, worktree_path,
    )
    _emit_event(session_id, "workspace_provisioned",
                f"Auto-provisioned workspace from {Path(repo_path).name}",
                {"repo_path": repo_path, "worktree_path": worktree_path})

    return (worktree_path, branch)


async def _execute_direct_action(
    session_id: str,
    task_id: str,
    action: str,
    instruction: str,
) -> TaskHandle:
    """Execute a deterministic desktop action without LLM.

    Directly spawns the requested process (terminal, browser, file manager)
    and returns immediately. No agent loop, no planning.
    """
    import subprocess

    _emit_event(session_id, "action_started", f"Executing: {action}", {
        "task_id": task_id, "direct_action": action, "executor": "direct",
    })

    start = time.time()

    # Desktop env: xrdp session runs on :10 with agent's Xauthority
    desktop_env = {
        **os.environ,
        "DISPLAY": os.environ.get("DISPLAY", ":10"),
        "XAUTHORITY": os.environ.get("XAUTHORITY", "/home/agent/.Xauthority"),
    }

    if action == "open_terminal":
        terminal_cmds = [
            ["xfce4-terminal"],
            ["xterm"],
            ["gnome-terminal"],
            ["x-terminal-emulator"],
        ]
        opened = False
        for cmd in terminal_cmds:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=desktop_env,
                )
                opened = True
                break
            except FileNotFoundError:
                continue

        if not opened:
            raise RuntimeError("No terminal emulator found (tried xfce4-terminal, xterm, gnome-terminal)")

        summary = "Opened terminal on desktop"

    elif action == "open_browser":
        import re
        url_match = re.search(r'https?://\S+', instruction)
        url = url_match.group(0) if url_match else ""
        cmd = ["xdg-open", url] if url else ["xdg-open", "about:blank"]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=desktop_env,
            )
        except FileNotFoundError:
            raise RuntimeError("xdg-open not found")
        summary = f"Opened browser{' to ' + url if url else ''}"

    elif action == "open_file_manager":
        try:
            subprocess.Popen(
                ["xdg-open", "."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=desktop_env,
            )
        except FileNotFoundError:
            raise RuntimeError("xdg-open not found")
        summary = "Opened file manager"

    elif action == "take_screenshot":
        screenshot_dir = _sessions_dir() / session_id / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"screenshot-{int(time.time())}.png"
        try:
            subprocess.run(
                ["scrot", str(screenshot_path)],
                timeout=10,
                env=desktop_env,
            )
        except FileNotFoundError:
            subprocess.run(
                ["import", "-window", "root", str(screenshot_path)],
                timeout=10,
                env=desktop_env,
            )
        summary = f"Screenshot saved: {screenshot_path.name}"

    else:
        raise ValueError(f"Unknown direct action: {action}")

    duration = time.time() - start
    _emit_event(session_id, "action_completed", summary, {
        "task_id": task_id,
        "direct_action": action,
        "executor": "direct",
        "duration_seconds": round(duration, 2),
    })

    return TaskHandle(
        task_id=task_id,
        session_id=session_id,
        state=TaskState.COMPLETED,
        routing_decision="direct_action",
        message=summary,
        metadata={"executor": "direct", "action": action, "duration_seconds": round(duration, 2)},
    )


async def _execute_via_agentic(
    session_id: str,
    instruction: str,
    task_id: str,
    model: str = "",
    execution_mode: str = "finite",
) -> dict[str, Any]:
    """Execute instruction via the AgenticExecutor.

    Uses LLM tool-calling loop to inspect, edit, and run commands.
    Executes directly on host filesystem — no Docker runtime needed.
    """
    from execution.agentic_executor import AgenticExecutor

    session_dir = _sessions_dir() / session_id

    import json as _json
    worktree_path = ""
    branch = ""
    # Try session.json first (current format), then meta.json (legacy)
    for filename in ("session.json", "meta.json"):
        candidate = session_dir / filename
        if candidate.exists():
            try:
                meta = _json.loads(candidate.read_text())
                # Prefer worktree_path (isolated worktree) over repo_path (bare repo)
                worktree_path = meta.get("worktree_path", "") or meta.get("repo_path", "")
                branch = meta.get("branch", "")
                break
            except Exception:
                pass

    if not worktree_path or not Path(worktree_path).exists():
        # Auto-recovery: provision workspace from DEFAULT_REPO_PATH
        worktree_path, branch = _auto_provision_workspace(session_id, session_dir)
        if not worktree_path:
            return {
                "status": "failed",
                "summary": "No valid workspace found for session. Set DEFAULT_REPO_PATH or create session with a repo.",
                "files_edited": [],
                "duration_seconds": 0,
            }

    adapter = AgenticExecutor()

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

    def _event_bridge(event_type: str, message: str, metadata: dict | None = None):
        _emit_event(session_id, event_type, message, metadata or {})

    start = time.time()
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _agent_executor, adapter.run_task, session_id, packet, _event_bridge,
        )
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
