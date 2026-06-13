"""
Session controller — orchestrates prompt intake, routing, and session lifecycle.

Handles:
  POST /api/sessions                  — create a new session
  POST /api/sessions/:id/prompts      — submit a prompt while work is running
  POST /api/sessions/:id/control      — pause/resume/cancel/commit

This module owns the decision layer. It delegates to:
  - prompt_router for routing decisions
  - agent_core_client for next-action recommendations/outcome recording
  - WorkflowAdapter for durable execution of the locally wrapped next action
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

from adapters.workflow.base import WorkflowAdapter
from agent_core_client.client import AgentCoreClient
from execution.ambient_prompt_context import (
    ambient_packet_to_agent_core_context,
    ambient_packet_to_prompt_block,
    load_ambient_context_packet,
)
from execution.next_suggested_plan import NextSuggestedPlanError, next_suggestion_to_plan
from live_feed.events import EventStore, EventType, create_event
from prompt_router.router import RoutingDecision, RoutingInput, RoutingOutput, route_prompt, route_prompt_async
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
    """Orchestrates session lifecycle and prompt routing.

    Uses recommend-next as the advisory source of truth. The controller wraps the
    single recommended action in a one-step executor shell because the existing
    workflow executor consumes plan-shaped input.
    """

    def __init__(
        self,
        sessions_dir: str | Path = "/opt/workstation/sessions",
        agent_core_client: AgentCoreClient | None = None,
        workflow_adapter: WorkflowAdapter | None = None,
    ):
        self.session_store = SessionStore(sessions_dir)
        self.event_store = EventStore(sessions_dir)
        self.sessions_dir = Path(sessions_dir)
        self.agent_core_client = agent_core_client
        self.workflow_adapter = workflow_adapter

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

        if request.parent_session_id:
            parent = self.session_store.get(request.parent_session_id)
            if parent:
                session.root_session_id = parent.root_session_id or parent.session_id
        else:
            session.root_session_id = session.session_id

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

    async def handle_prompt(
        self, session_id: str, request: PromptRequest
    ) -> dict[str, Any]:
        """Handle a prompt submitted while work may be running."""
        session = self.session_store.get(session_id)
        if session is None:
            return {"error": f"Session {session_id} not found."}

        prompt_event = create_event(
            EventType.USER_PROMPT_RECEIVED,
            session_id,
            prompt=request.prompt,
            user_intent_hint=request.user_intent_hint,
        )
        self.event_store.append(prompt_event)

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

        routing_output = await route_prompt_async(routing_input)

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

        return await self._execute_routing_decision(session, routing_output, request.prompt)

    async def handle_control(
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
            if self.workflow_adapter:
                await self.workflow_adapter.pause(session_id)
            self.event_store.append(
                create_event(EventType.PLAN_PAUSED, session_id)
            )
            return {"status": "paused", "message": "Session paused."}

        if command == "resume":
            session.status = SessionStatus.EDITING
            self.session_store.save(session)
            if self.workflow_adapter:
                await self.workflow_adapter.resume(session_id)
            self.event_store.append(
                create_event(EventType.PLAN_RESUMED, session_id)
            )
            return {"status": "resumed", "message": "Session resumed."}

        if command == "cancel":
            session.status = SessionStatus.CANCELLED
            self.session_store.save(session)
            if self.workflow_adapter:
                await self.workflow_adapter.cancel(session_id)
            self.event_store.append(
                create_event(EventType.PLAN_CANCELLED, session_id)
            )
            return {"status": "cancelled", "message": "Session cancelled."}

        if command == "commit_checkpoint":
            return {
                "status": "commit_requested",
                "message": "Commit checkpoint requested; pending platform validation.",
            }

        return {"error": f"Unknown control command: {command}"}

    async def _request_next_action_and_start_workflow(
        self,
        session: Session,
        prompt: str,
        mode_preference: str = "finite",
    ) -> dict[str, Any]:
        """Request one next suggested action, wrap it, validate it, and start the workflow."""
        session_id = session.session_id

        if self.agent_core_client is None:
            return {"error": "agent-core recommend-next client not configured"}

        if self.workflow_adapter is None:
            return {"error": "workflow adapter not configured"}

        ambient_packet = load_ambient_context_packet(
            session_id,
            goal=prompt,
            sessions_dir=self.sessions_dir,
        )
        ambient_context = ambient_packet_to_agent_core_context(ambient_packet)
        ambient_prompt_block = ambient_packet_to_prompt_block(ambient_packet)

        self.session_store.update_status(session_id, SessionStatus.PLANNING)
        self.event_store.append(
            create_event(
                EventType.PLAN_REQUESTED,
                session_id,
                prompt=prompt,
                mode_preference=mode_preference,
                recommendation_source="recommend_next",
                ambient_context_attached=bool(ambient_context),
                source_candidate_count=len(ambient_context.get("source_candidates", [])),
                evidence_event_ids=ambient_context.get("evidence_event_ids", []),
                ambient_prompt_context=ambient_prompt_block[:4000],
            )
        )

        completed_actions = self._get_completed_actions(session_id)
        current_action = self._get_current_action(session_id) or prompt
        try:
            recommendation = await self.agent_core_client.recommend_next(
                task_type="implementation",
                current_action=current_action,
                completed_actions=completed_actions,
                session_id=session_id,
                repo_id=session.repo_id,
                ambient_context=ambient_context,
            )
        except Exception as e:
            self.event_store.append(
                create_event(
                    EventType.PLAN_VALIDATION_FAILED,
                    session_id,
                    error=str(e),
                    source="recommend_next",
                )
            )
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": f"recommend-next request failed: {e}"}

        if recommendation.get("ok") is False:
            error_msg = recommendation.get("error", "recommend-next failed")
            self.event_store.append(
                create_event(
                    EventType.PLAN_VALIDATION_FAILED,
                    session_id,
                    error=error_msg,
                    source="recommend_next_response",
                )
            )
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": error_msg, "recommendation": recommendation}

        try:
            plan = next_suggestion_to_plan(
                prompt=prompt,
                recommendation=recommendation,
                mode_preference=mode_preference,
            )
            self._validate_one_step_plan_for_session(session, plan)
        except NextSuggestedPlanError as e:
            self.event_store.append(
                create_event(
                    EventType.PLAN_VALIDATION_FAILED,
                    session_id,
                    error=str(e),
                    source="next_suggested_plan_adapter",
                )
            )
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": f"Next suggested action validation failed: {e}", "recommendation": recommendation}

        action_contract_validation = await self._validate_next_action_contract(session_id, plan["steps"][0])
        if action_contract_validation is not None:
            return action_contract_validation

        self.event_store.append(
            create_event(
                EventType.PLAN_GENERATED,
                session_id,
                plan=plan,
                warnings=recommendation.get("warnings", []),
                source="next_suggested_plan",
                recommendation=recommendation,
                ambient_context_attached=bool(ambient_context),
                source_candidate_count=len(ambient_context.get("source_candidates", [])),
            )
        )

        context = {
            "repo_id": session.repo_id,
            "worktree_id": session.worktree_id,
            "allowed_actions": session.allowed_actions,
            "ambient_context": ambient_context,
            "ambient_prompt_context": ambient_prompt_block,
            "recommendation_source": "recommend_next",
        }
        try:
            workflow_result = await self.workflow_adapter.start_plan(
                session_id, plan, context
            )
        except Exception as e:
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": f"Workflow start failed: {e}"}

        self.event_store.append(
            create_event(
                EventType.PLAN_STARTED,
                session_id,
                backend=workflow_result.get("backend", ""),
                workflow_run_id=workflow_result.get("workflow_run_id", ""),
                ambient_context_attached=bool(ambient_context),
                source="next_suggested_plan",
            )
        )
        self.session_store.update_status(session_id, SessionStatus.EDITING)

        return {
            "plan": plan,
            "next_suggested_action": plan["steps"][0],
            "recommendation": recommendation,
            "workflow": workflow_result,
            "ambient_context": ambient_context,
            "message": "Next suggested action wrapped and workflow started.",
        }

    async def _validate_next_action_contract(self, session_id: str, step: dict[str, Any]) -> dict[str, Any] | None:
        action_name = str(step.get("action_name") or "")
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        try:
            validation = await self.agent_core_client.validate_action(action_name, params)  # type: ignore[union-attr]
        except Exception as e:
            self.event_store.append(
                create_event(
                    EventType.PLAN_VALIDATION_FAILED,
                    session_id,
                    error=str(e),
                    source="recommend_next_validate_action",
                )
            )
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": f"Next suggested action contract validation failed: {e}"}

        if validation.get("ok") is False or validation.get("valid") is False:
            errors = validation.get("errors", [])
            error_msg = validation.get("error") or ("; ".join(map(str, errors)) if errors else "Next suggested action contract validation failed")
            self.event_store.append(
                create_event(
                    EventType.PLAN_VALIDATION_FAILED,
                    session_id,
                    error=error_msg,
                    errors=errors,
                    source="recommend_next_validate_action_response",
                )
            )
            self.session_store.update_status(session_id, SessionStatus.FAILED)
            return {"error": error_msg, "action_validation": validation}
        return None

    def _validate_one_step_plan_for_session(self, session: Session, plan: dict[str, Any]) -> None:
        steps = plan.get("steps")
        if not isinstance(steps, list) or len(steps) != 1:
            raise NextSuggestedPlanError("recommend-next must produce exactly one action")
        step = steps[0]
        if not isinstance(step, dict):
            raise NextSuggestedPlanError("recommend-next action step must be an object")
        action_name = str(step.get("action_name") or "").strip()
        if not action_name:
            raise NextSuggestedPlanError("recommend-next action is missing action_name")
        if session.allowed_actions and action_name not in session.allowed_actions:
            raise NextSuggestedPlanError(f"Action {action_name} is not in session allowed_actions")

    async def _execute_routing_decision(
        self,
        session: Session,
        routing: RoutingOutput,
        prompt: str,
    ) -> dict[str, Any]:
        decision = routing.decision

        if decision == RoutingDecision.INTERRUPT_CURRENT:
            return await self.handle_control(
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
            child_id = child_result["session"]["session_id"]
            child_session = self.session_store.get(child_id)
            plan_result = {}
            if child_session and self.agent_core_client and self.workflow_adapter:
                plan_result = await self._request_next_action_and_start_workflow(child_session, prompt)
            return {
                "routing": routing.to_dict(),
                "child_session": child_result["session"],
                "plan": plan_result,
                "message": "Started a child session because this is a separate task.",
            }

        if decision == RoutingDecision.SPAWN_NEW_SESSION:
            new_result = self.create_session(
                CreateSessionRequest(
                    prompt=prompt,
                    session_type="root_session",
                )
            )
            new_id = new_result["session"]["session_id"]
            new_session = self.session_store.get(new_id)
            plan_result = {}
            if new_session and self.agent_core_client and self.workflow_adapter:
                plan_result = await self._request_next_action_and_start_workflow(new_session, prompt)
            return {
                "routing": routing.to_dict(),
                "new_session": new_result["session"],
                "plan": plan_result,
                "message": "Started a new session for this task.",
            }

        if decision == RoutingDecision.QUEUE:
            return {
                "routing": routing.to_dict(),
                "message": "Queued until the current operation finishes.",
            }

        plan_result = {}
        if self.agent_core_client and self.workflow_adapter:
            mode = "finite"
            if decision == RoutingDecision.MODIFY_CURRENT_PLAN:
                mode = "finite"
            plan_result = await self._request_next_action_and_start_workflow(session, prompt, mode)

        return {
            "routing": routing.to_dict(),
            "session_id": session.session_id,
            "plan": plan_result,
            "message": _user_message(decision),
        }

    def _infer_plan_status(self, session: Session) -> str:
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
        evt = self.event_store.get_latest_event(
            session_id, EventType.ACTION_STARTED
        )
        if evt:
            return evt.get("data", {}).get("action_name", "")
        return ""

    def _get_completed_actions(self, session_id: str) -> list[str]:
        events = self.event_store.get_events(session_id, limit=100)
        completed: list[str] = []
        for event in events:
            if event.get("event_type") != EventType.ACTION_COMPLETED.value:
                continue
            action_name = event.get("data", {}).get("action_name", "")
            if action_name:
                completed.append(action_name)
        return completed


def _user_message(decision: RoutingDecision) -> str:
    messages = {
        RoutingDecision.APPEND_TO_CURRENT: "Requesting the next suggested action for this instruction.",
        RoutingDecision.MODIFY_CURRENT_PLAN: "Requesting the next suggested action for the revised instruction.",
        RoutingDecision.INTERRUPT_CURRENT: "Interrupting the current plan.",
        RoutingDecision.SPAWN_CHILD_SESSION: "Started a child session.",
        RoutingDecision.SPAWN_NEW_SESSION: "Started a new session.",
        RoutingDecision.QUEUE: "Queued until the current operation finishes.",
    }
    return messages.get(decision, "Prompt received.")
