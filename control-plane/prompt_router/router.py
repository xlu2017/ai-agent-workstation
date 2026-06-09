"""
Prompt router — decides what to do with a new user prompt while work is running.

Routing decisions:
  append_to_current     — clarification or small correction
  modify_current_plan   — new instruction about the same goal
  interrupt_current     — stop/pause/cancel
  spawn_child_session   — different goal but same repo/context
  spawn_new_session     — different repo or unrelated goal
  queue                 — current session in non-interruptible operation

This module uses an LLM to classify routing decisions. Control commands
(stop/pause/resume/cancel) are detected by regex first as a fast path.
If the LLM is unavailable, falls back to heuristic routing.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "deepseek-v4-flash")
ROUTER_LLM_ENABLED = os.environ.get("ROUTER_LLM_ENABLED", "true").lower() == "true"


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
    # Deterministic classifier fields
    task_class: str = ""           # "desktop_control", "code_implementation", ""
    direct_action: str = ""        # "open_terminal", "open_browser", etc.
    classification_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "decision": self.decision.value,
            "rationale": self.rationale,
            "target_session_id": self.target_session_id,
            "requires_user_confirmation": self.requires_user_confirmation,
            "control_command": self.control_command,
        }
        if self.task_class:
            d["task_class"] = self.task_class
        if self.direct_action:
            d["direct_action"] = self.direct_action
        if self.classification_confidence > 0:
            d["classification_confidence"] = self.classification_confidence
        return d


# ── Control command detection (fast path, no LLM) ────────────────

CONTROL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(stop|cancel|abort)\b", re.I), "cancel"),
    (re.compile(r"^pause\b", re.I), "pause"),
    (re.compile(r"^resume\b", re.I), "resume"),
    (re.compile(r"^continue\b", re.I), "continue"),
    (re.compile(r"^commit\s+what\s+is\s+done\b", re.I), "commit_checkpoint"),
    (re.compile(r"^(start\s+a\s+new\s+session|new\s+session)\b", re.I), "new_session"),
    (re.compile(r"^(run\s+.*\s+in\s+parallel|parallel)\b", re.I), "parallel"),
]


def detect_control_command(prompt: str) -> str | None:
    """Check if the prompt is a control command. Returns command name or None."""
    stripped = prompt.strip()
    for pattern, command in CONTROL_PATTERNS:
        if pattern.search(stripped):
            return command
    return None


# ── LLM routing prompt ───────────────────────────────────────────

ROUTING_SYSTEM_PROMPT = """You are a prompt routing classifier for an autonomous coding agent platform.

Given a user prompt and the current session state, classify the prompt into exactly one routing decision.

## Routing decisions

- **append_to_current**: The user is adding a clarification, follow-up instruction, or small correction to the current task. The existing plan can continue with this additional context.
- **modify_current_plan**: The user wants to change the approach, add significant new requirements, or redirect the current work. The plan needs to be regenerated.
- **interrupt_current**: The user wants to stop, pause, or cancel the current work. (Note: explicit control commands like "stop"/"pause"/"cancel" are handled before reaching you.)
- **spawn_child_session**: The user is requesting a separate task in the same repository. This is a different goal that should run in its own session but shares the repo context.
- **spawn_new_session**: The user is requesting work in a different repository or a completely unrelated task.
- **queue**: The current session is in a critical operation (e.g., mid-commit, mid-test) and the new prompt should wait.

## Guidelines

- If no plan is active (status: none/completed), use **append_to_current** — treat the prompt as a new task.
- Short follow-ups like "also do X" or "don't forget Y" during an active plan are **modify_current_plan** if they change what the plan should do, or **append_to_current** if they're just additional context.
- "New task:", "different task:", "work on another thing" → **spawn_child_session** if same repo, **spawn_new_session** if different/unspecified repo.
- If the user is asking about a completely different project/repo → **spawn_new_session**.
- Use **queue** only when explicitly told the session is in a non-interruptible state (validating, committing).

Respond with a JSON object:
```json
{
  "decision": "<one of the six decisions>",
  "rationale": "<brief explanation>"
}
```"""


def _build_routing_user_prompt(input: RoutingInput) -> str:
    """Build the user message for the LLM routing call."""
    parts = [f"**User prompt**: {input.prompt}"]

    parts.append(f"**Plan status**: {input.current_plan_status or 'none'}")

    if input.current_action:
        parts.append(f"**Current action**: {input.current_action}")

    if input.repo_id:
        parts.append(f"**Repo**: {input.repo_id}")

    if input.user_intent_hint:
        parts.append(f"**User intent hint**: {input.user_intent_hint}")

    # Include last few event types for context
    if input.recent_events:
        recent_types = [
            e.get("event_type", "unknown") for e in input.recent_events[-5:]
        ]
        parts.append(f"**Recent events**: {', '.join(recent_types)}")

    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────

async def _call_llm_router(input: RoutingInput) -> RoutingOutput | None:
    """Call the LLM to classify the routing decision.

    Returns None if the LLM is unavailable or the response can't be parsed,
    so the caller can fall back to heuristics.
    """
    if not ROUTER_LLM_ENABLED:
        return None

    user_msg = _build_routing_user_prompt(input)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if LITELLM_KEY:
                headers["Authorization"] = f"Bearer {LITELLM_KEY}"

            resp = await client.post(
                f"{LITELLM_URL}/v1/chat/completions",
                headers=headers,
                json={
                    "model": ROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        decision_str = parsed.get("decision", "")
        rationale = parsed.get("rationale", "LLM routing")

        try:
            decision = RoutingDecision(decision_str)
        except ValueError:
            logger.warning("LLM returned unknown decision: %s", decision_str)
            return None

        return RoutingOutput(
            decision=decision,
            rationale=f"[LLM] {rationale}",
            target_session_id=input.session_id,
        )

    except Exception as e:
        logger.debug("LLM routing failed, falling back to heuristics: %s", e)
        return None


# ── Heuristic fallback ───────────────────────────────────────────

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


def _heuristic_route(input: RoutingInput) -> RoutingOutput:
    """Fallback heuristic router when LLM is unavailable."""
    prompt = input.prompt.strip()

    # If no plan is running, append to current
    if input.current_plan_status in ("", "none", "completed"):
        return RoutingOutput(
            decision=RoutingDecision.APPEND_TO_CURRENT,
            rationale="[heuristic] No active plan. Starting new work in this session.",
            target_session_id=input.session_id,
        )

    # Check for same-goal modifications
    for pattern in SAME_GOAL_PATTERNS:
        if pattern.search(prompt):
            return RoutingOutput(
                decision=RoutingDecision.MODIFY_CURRENT_PLAN,
                rationale="[heuristic] Prompt appears to modify/extend the current goal.",
                target_session_id=input.session_id,
            )

    # Check for new/different goal
    for pattern in NEW_GOAL_PATTERNS:
        if pattern.search(prompt):
            if input.repo_id:
                return RoutingOutput(
                    decision=RoutingDecision.SPAWN_CHILD_SESSION,
                    rationale="[heuristic] Different goal in the same repo context.",
                    target_session_id=input.session_id,
                )
            return RoutingOutput(
                decision=RoutingDecision.SPAWN_NEW_SESSION,
                rationale="[heuristic] Unrelated goal, spawning new session.",
            )

    # Short prompt during active plan → clarification
    if len(prompt.split()) <= 15 and input.current_plan_status == "running":
        return RoutingOutput(
            decision=RoutingDecision.APPEND_TO_CURRENT,
            rationale="[heuristic] Short prompt during active plan — treating as clarification.",
            target_session_id=input.session_id,
        )

    # Default: modify current plan
    if input.current_plan_status == "running":
        return RoutingOutput(
            decision=RoutingDecision.MODIFY_CURRENT_PLAN,
            rationale="[heuristic] New instructions during active plan — modifying plan.",
            target_session_id=input.session_id,
        )

    # Fallback: append
    return RoutingOutput(
        decision=RoutingDecision.APPEND_TO_CURRENT,
        rationale="[heuristic] Default: appending to current session.",
        target_session_id=input.session_id,
    )


# ── Main entry points ────────────────────────────────────────────

def _handle_control(input: RoutingInput, control_cmd: str) -> RoutingOutput:
    """Handle a detected control command."""
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
    # Unknown control command — fall through
    return RoutingOutput(
        decision=RoutingDecision.APPEND_TO_CURRENT,
        rationale=f"Unknown control command: {control_cmd}",
        target_session_id=input.session_id,
    )


async def route_prompt_async(input: RoutingInput) -> RoutingOutput:
    """Route a user prompt.

    Flow:
    1. Check for control commands (regex fast path)
    2. Deterministic fuzzy classifier for direct platform actions
    3. LLM classification (ambiguity resolver, not primary path)
    4. Heuristic fallback
    """
    prompt = input.prompt.strip()

    # 1. Control commands — fast path
    control_cmd = detect_control_command(prompt)
    if control_cmd:
        return _handle_control(input, control_cmd)

    # 2. Deterministic direct-action classifier — primary fast path
    from prompt_router.deterministic_classifier import (
        AMBIGUOUS_THRESHOLD,
        classify_direct_action,
        should_execute_directly,
    )

    classification = classify_direct_action(prompt)

    if not classification.is_code_intent and should_execute_directly(classification):
        logger.info(
            "Deterministic route: %s (%.2f) for '%s'",
            classification.action_name,
            classification.confidence,
            prompt[:80],
        )
        return RoutingOutput(
            decision=RoutingDecision.APPEND_TO_CURRENT,
            rationale=(
                f"[deterministic] Direct action: {classification.action_name} "
                f"(confidence={classification.confidence:.2f})"
            ),
            target_session_id=input.session_id,
            task_class=classification.task_class,
            direct_action=classification.action_name,
            classification_confidence=classification.confidence,
        )

    # If code-intent was detected, skip LLM for routing — go straight to heuristic
    # (the prompt is clearly about implementation, not a direct desktop action)
    if classification.is_code_intent:
        logger.debug(
            "Code-intent detected ('%s') for '%s' — using heuristic route",
            classification.negative_match,
            prompt[:80],
        )
        result = _heuristic_route(input)
        result.task_class = "code_implementation"
        return result

    # If medium confidence, let LLM disambiguate
    if classification.confidence >= AMBIGUOUS_THRESHOLD:
        logger.debug(
            "Ambiguous classification: %s (%.2f) — trying LLM",
            classification.action_name,
            classification.confidence,
        )

    # 3. Try LLM routing (demoted to ambiguity resolver)
    llm_result = await _call_llm_router(input)
    if llm_result is not None:
        return llm_result

    # 4. Heuristic fallback
    return _heuristic_route(input)


def route_prompt(input: RoutingInput) -> RoutingOutput:
    """Synchronous heuristic-only router (for backward compatibility).

    Used when async context is not available. Prefer route_prompt_async().
    """
    prompt = input.prompt.strip()

    control_cmd = detect_control_command(prompt)
    if control_cmd:
        return _handle_control(input, control_cmd)

    return _heuristic_route(input)
