"""
Session controller — orchestrates prompt intake, routing, and session lifecycle.

Handles:
  POST /api/sessions                  — create a new session
  POST /api/sessions/:id/prompts      — submit a prompt while work is running
  POST /api/sessions/:id/control      — pause/resume/cancel/commit

This module owns the decision layer. It delegates to:
  - prompt_router for routing decisions
  - agent_core_client for plan generation/validation/outcome recording
  - live_feed/events for event logging
  - sessions/models for session persistence
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from live_feed.events import EventStore, EventType, create_event
from prompt_router.router import RoutingInput, RoutingOutput, route_prompt
from sessions.models import Session, SessionStatus, SessionStore, SessionType


REPOS_DIR = Path("/opt/workstation/repos")
DEFAULT_ALLOWED_ACTIONS = [
    "classify_task",
    "retrieve_context",
    "search_memory",
    "grep",
    "read_file",
    "identify_relevant_tests",
    "apply_patch",
    "run_tests",
    "summarize_diff",
    "request_approval",
    "commit",
]


class CreateSessionRequest(BaseModel):
    prompt: str
    repo_id: str = ""
    session_type: str = "root_session"
    parent_session_id: str = ""
    allowed_actions: list[str] = []
    worktree_id: str = ""
    executor_id: str = ""


class PromptRequest(BaseModel):
    prompt: str
    user_intent_hint: str = ""


class ControlRequest(BaseModel):
    command: str  # pause, resume, cancel, commit_checkpoint


class SessionController:
    """Orchestrates session lifecycle and prompt routing."""

    def __init__(
        self,
        sessions_dir: str | Path = "/opt/workstation/sessions",
    ):
        self.session_store = SessionStore(sessions_dir)
        self.event_store = EventStore(sessions_dir)
        self.sessions_dir = Path(sessions_dir)

    def create_session(self, request: CreateSessionRequest) -> dict[str, Any]:
        """Create a new session."""
        session = Session(
            session_type=SessionType(request.session_type),
            status=SessionStatus.CREATED,
            repo_id=request.repo_id,
            worktree_id=request.worktree_id or "",
            executor_id=request.executor_id or "",
            parent_session_id=request.parent_session_id,
            root_session_id=request.parent_session_id or "",
            prompt=request.prompt,
            allowed_actions=request.allowed_actions or DEFAULT_ALLOWED_ACTIONS,
        )

        # For child sessions, inherit root_session_id from parent
        if request.parent_session_id:
            parent = self.session_store.get(request.parent_session_id)
            if parent:
                session.root_session_id = parent.root_session_id or parent.session_id
        else:
            session.root_session_id = session.session_id

        # Create worktree for mutating sessions
        if request.repo_id and not session.worktree_id:
            worktree_id = f"worktree-{session.session_id}"
            worktree_path = REPOS_DIR / worktree_id
            repo_path = REPOS_DIR / request.repo_id
            if repo_path.exists():
                branch = f"{session.session_id}-branch"
                result = subprocess.run(
                    ["git", "worktree", "add", str(worktree_path), "-b", branch],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    session.worktree_id = worktree_id

        self.session_store.save(session)

        # Record creation event
        self.event_store.append(
            create_event(
                EventType.USER_PROMPT_RECEIVED,
                session.session_id,
                prompt=request.prompt,
                session_type=session.session_type.value,
            )
        )

        return {
            "session": session.to_dict(),
            "message": f"Session {session.session_id} created.",
        }

    def handle_prompt(
        self, session_id: str, request: PromptRequest
    ) -> dict[str, Any]:
        """Handle a prompt submitted while work may be running.

        1. Record user_prompt_received event
        2. Load session state
        3. Route prompt
        4. Record routing_decision_made event
        5. Return routing decision
        """
        session = self.session_store.get(session_id)
        if session is None:
            return {"error": f"Session {session_id} not found."}

        # 1. Record prompt received
        prompt_event = create_event(
            EventType.USER_PROMPT_RECEIVED,
            session_id,
            prompt=request.prompt,
            user_intent_hint=request.user_intent_hint,
        )
        self.event_store.append(prompt_event)

        # 2. Build routing input from session state
        plan_status = self._infer_plan_status(session)
        current_action = self._get_current_action(session_id)
        recent_events = self.event_store.get_events(
            session_id, limit=10
        )

        routing_input = RoutingInput(
            session_id=session_id,
            prompt=request.prompt,
            current_plan_status=plan_status,
            current_action=current_action,
            repo_id=session.repo_id,
            worktree_id=session.worktree_id,
            recent_events=recent_events,
            user_intent_hint=request.user_intent_hint,
        )

        # 3. Route
        routing_output = route_prompt(routing_input)

        # 4. Record routing decision
        self.event_store.append(
            create_event(
                EventType.ROUTING_DECISION_MADE,
                session_id,
                decision=routing_output.decision.value,
                rationale=routing_output.rationale,
                target_session_id=routing_output.target_session_id,
                control_command=routing_output.control_command,
            )
        )

        # 5. Execute the routing decision
        result = self._execute_routing_decision(session, routing_output, request.prompt)

        return result

    def handle_control(
        self, session_id: str, request: ControlRequest
    ) -> dict[str, Any]:
        """Handle a control command (pause/resume/cancel/commit)."""
        session = self.session_store.get(session_id)
        if session is None:
            return {"error": f"Session {session_id} not found."}

        command = request.command.lower()

        if command == "pause":
            session.status = SessionStatus.PAUSED
            self.session_store.save(session)
            self.event_store.append(
                create_event(EventType.PLAN_PAUSED, session_id)
            )
            return {"status": "paused", "message": "Session paused."}

        elif command == "resume":
            session.status = SessionStatus.EDITING
            self.session_store.save(session)
            self.event_store.append(
                create_event(EventType.PLAN_RESUMED, session_id)
            )
            return {"status": "resumed", "message": "Session resumed."}

        elif command == "cancel":
            session.status = SessionStatus.CANCELLED
            self.session_store.save(session)
            self.event_store.append(
                create_event(EventType.PLAN_CANCELLED, session_id)
            )
            return {"status": "cancelled", "message": "Session cancelled."}

        elif command == "commit_checkpoint":
            self.event_store.append(
                create_event(
                    EventType.COMMIT_CREATED,
                    session_id,
                    trigger="user_request",
                )
            )
            return {
                "status": "commit_requested",
                "message": "Commit checkpoint requested. Platform will commit validated changes.",
            }

        return {"error": f"Unknown control command: {command}"}

    def _infer_plan_status(self, session: Session) -> str:
        """Infer plan status from session status."""
        status_map = {
            SessionStatus.EDITING: "running",
            SessionStatus.VALIDATING: "running",
            SessionStatus.PLANNING: "running",
            SessionStatus.PAUSED: "paused",
            SessionStatus.COMPLETED: "completed",
            SessionStatus.CANCELLED: "completed",
            SessionStatus.FAILED: "completed",
        }
        return status_map.get(session.status, "none")

    def _get_current_action(self, session_id: str) -> str:
        """Get the most recent action_started event."""
        evt = self.event_store.get_latest_event(
            session_id, EventType.ACTION_STARTED
        )
        if evt:
            return evt.get("data", {}).get("action_name", "")
        return ""

    def _execute_routing_decision(
        self,
        session: Session,
        routing: RoutingOutput,
        prompt: str,
    ) -> dict[str, Any]:
        """Execute the routing decision."""
        decision = routing.decision

        if decision == RoutingDecision.INTERRUPT_CURRENT:
            return self.handle_control(
                session.session_id,
                ControlRequest(command=routing.control_command or "pause"),
            )

        if decision == RoutingDecision.SPAWN_CHILD_SESSION:
            child_result = self.create_session(
                CreateSessionRequest(
                    prompt=prompt,
                    repo_id=session.repo_id,
                    session_type="child_session",
                    parent_session_id=session.session_id,
                    allowed_actions=session.allowed_actions,
                )
            )
            self.event_store.append(
                create_event(
                    EventType.CHILD_SESSION_STARTED,
                    session.session_id,
                    child_session_id=child_result["session"]["session_id"],
                    prompt=prompt,
                )
            )
            return {
                "routing": routing.to_dict(),
                "child_session": child_result["session"],
                "message": "Started a child session because this is a separate task.",
            }

        if decision == RoutingDecision.SPAWN_NEW_SESSION:
            new_result = self.create_session(
                CreateSessionRequest(
                    prompt=prompt,
                    session_type="root_session",
                )
            )
            return {
                "routing": routing.to_dict(),
                "new_session": new_result["session"],
                "message": "Started a new session for this task.",
            }

        if decision == RoutingDecision.QUEUE:
            return {
                "routing": routing.to_dict(),
                "message": "Queued until the current operation finishes.",
            }

        # APPEND_TO_CURRENT or MODIFY_CURRENT_PLAN
        return {
            "routing": routing.to_dict(),
            "session_id": session.session_id,
            "message": _user_message(decision),
        }


# Import here to avoid circular import
from prompt_router.router import RoutingDecision


def _user_message(decision: RoutingDecision) -> str:
    messages = {
        RoutingDecision.APPEND_TO_CURRENT: "Added this instruction to the current plan.",
        RoutingDecision.MODIFY_CURRENT_PLAN: "Modifying the current plan with new instructions.",
        RoutingDecision.INTERRUPT_CURRENT: "Interrupting the current plan.",
        RoutingDecision.SPAWN_CHILD_SESSION: "Started a child session.",
        RoutingDecision.SPAWN_NEW_SESSION: "Started a new session.",
        RoutingDecision.QUEUE: "Queued until the current operation finishes.",
    }
    return messages.get(decision, "Prompt received.")
