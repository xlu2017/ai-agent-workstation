"""
Prompt router — decides what to do with a new user prompt while work is running.

Routing decisions:
  append_to_current     — clarification or small correction
  modify_current_plan   — new instruction about the same goal
  interrupt_current     — stop/pause/cancel
  spawn_child_session   — different goal but same repo/context
  spawn_new_session     — different repo or unrelated goal
  queue                 — current session in non-interruptible operation

This module handles routing logic only. Execution of the decision
(actually spawning sessions, modifying plans, etc.) is handled by the
session controller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RoutingDecision(str, Enum):
    APPEND_TO_CURRENT = "append_to_current"
    MODIFY_CURRENT_PLAN = "modify_current_plan"
    INTERRUPT_CURRENT = "interrupt_current"
    SPAWN_CHILD_SESSION = "spawn_child_session"
    SPAWN_NEW_SESSION = "spawn_new_session"
    QUEUE = "queue"


@dataclass
class RoutingInput:
    session_id: str
    prompt: str
    current_plan_status: str = ""  # running, paused, completed, none
    current_action: str = ""
    repo_id: str = ""
    worktree_id: str = ""
    active_files: list[str] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    user_intent_hint: str = ""


@dataclass
class RoutingOutput:
    decision: RoutingDecision
    rationale: str
    target_session_id: str = ""
    requires_user_confirmation: bool = False
    control_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "rationale": self.rationale,
            "target_session_id": self.target_session_id,
            "requires_user_confirmation": self.requires_user_confirmation,
            "control_command": self.control_command,
        }


# Control command patterns
CONTROL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(stop|cancel|abort)\b", re.I), "cancel"),
    (re.compile(r"^pause\b", re.I), "pause"),
    (re.compile(r"^resume\b", re.I), "resume"),
    (re.compile(r"^continue\b", re.I), "continue"),
    (re.compile(r"^commit\s+what\s+is\s+done\b", re.I), "commit_checkpoint"),
    (re.compile(r"^(start\s+a\s+new\s+session|new\s+session)\b", re.I), "new_session"),
    (re.compile(r"^(run\s+.*\s+in\s+parallel|parallel)\b", re.I), "parallel"),
]

# Patterns that suggest the prompt is about the same goal
SAME_GOAL_PATTERNS = [
    re.compile(r"^also\b", re.I),
    re.compile(r"^and\b", re.I),
    re.compile(r"^(don'?t\s+forget|make\s+sure|remember)\b", re.I),
    re.compile(r"^(check|test|verify|validate)\b", re.I),
    re.compile(r"^(update|fix|change|modify|adjust)\s+(the|this)\b", re.I),
]

# Patterns that suggest a new/different goal
NEW_GOAL_PATTERNS = [
    re.compile(r"^(new\s+task|different\s+task|separate\s+task)\b", re.I),
    re.compile(r"^(work\s+on\s+another|switch\s+to)\b", re.I),
    re.compile(r"^(after\s+this|next|when\s+you'?re\s+done)\b", re.I),
    re.compile(r"^(migrate|rewrite|refactor\s+the\s+entire)\b", re.I),
]


def detect_control_command(prompt: str) -> str | None:
    """Check if the prompt is a control command. Returns command name or None."""
    stripped = prompt.strip()
    for pattern, command in CONTROL_PATTERNS:
        if pattern.search(stripped):
            return command
    return None


def route_prompt(input: RoutingInput) -> RoutingOutput:
    """Route a user prompt to the appropriate decision.

    This is a deterministic heuristic router. For more nuanced routing,
    the platform can call agent-core's LLM planner.
    """
    prompt = input.prompt.strip()

    # 1. Check for control commands first
    control_cmd = detect_control_command(prompt)
    if control_cmd:
        if control_cmd in ("cancel", "pause"):
            return RoutingOutput(
                decision=RoutingDecision.INTERRUPT_CURRENT,
                rationale=f"User issued control command: {control_cmd}",
                target_session_id=input.session_id,
                control_command=control_cmd,
            )
        if control_cmd == "resume":
            return RoutingOutput(
                decision=RoutingDecision.APPEND_TO_CURRENT,
                rationale="User requested resume.",
                target_session_id=input.session_id,
                control_command="resume",
            )
        if control_cmd == "continue":
            return RoutingOutput(
                decision=RoutingDecision.APPEND_TO_CURRENT,
                rationale="User requested continue.",
                target_session_id=input.session_id,
                control_command="continue",
            )
        if control_cmd == "commit_checkpoint":
            return RoutingOutput(
                decision=RoutingDecision.APPEND_TO_CURRENT,
                rationale="User requested committing current progress.",
                target_session_id=input.session_id,
                control_command="commit_checkpoint",
            )
        if control_cmd == "new_session":
            return RoutingOutput(
                decision=RoutingDecision.SPAWN_NEW_SESSION,
                rationale="User explicitly requested a new session.",
            )
        if control_cmd == "parallel":
            return RoutingOutput(
                decision=RoutingDecision.SPAWN_CHILD_SESSION,
                rationale="User requested parallel execution.",
                target_session_id=input.session_id,
            )

    # 2. If no plan is running, append to current
    if input.current_plan_status in ("", "none", "completed"):
        return RoutingOutput(
            decision=RoutingDecision.APPEND_TO_CURRENT,
            rationale="No active plan. Starting new work in this session.",
            target_session_id=input.session_id,
        )

    # 3. Check for same-goal modifications
    for pattern in SAME_GOAL_PATTERNS:
        if pattern.search(prompt):
            return RoutingOutput(
                decision=RoutingDecision.MODIFY_CURRENT_PLAN,
                rationale="Prompt appears to modify/extend the current goal.",
                target_session_id=input.session_id,
            )

    # 4. Check for new/different goal
    for pattern in NEW_GOAL_PATTERNS:
        if pattern.search(prompt):
            # If same repo, spawn child; otherwise new session
            if input.repo_id:
                return RoutingOutput(
                    decision=RoutingDecision.SPAWN_CHILD_SESSION,
                    rationale="Different goal in the same repo context.",
                    target_session_id=input.session_id,
                )
            return RoutingOutput(
                decision=RoutingDecision.SPAWN_NEW_SESSION,
                rationale="Unrelated goal, spawning new session.",
            )

    # 5. If plan is running and prompt is short (likely a clarification)
    if len(prompt.split()) <= 15 and input.current_plan_status == "running":
        return RoutingOutput(
            decision=RoutingDecision.APPEND_TO_CURRENT,
            rationale="Short prompt during active plan — treating as clarification.",
            target_session_id=input.session_id,
        )

    # 6. Default: modify current plan
    if input.current_plan_status == "running":
        return RoutingOutput(
            decision=RoutingDecision.MODIFY_CURRENT_PLAN,
            rationale="New instructions during active plan — modifying plan.",
            target_session_id=input.session_id,
        )

    # 7. Fallback: append
    return RoutingOutput(
        decision=RoutingDecision.APPEND_TO_CURRENT,
        rationale="Default: appending to current session.",
        target_session_id=input.session_id,
    )
