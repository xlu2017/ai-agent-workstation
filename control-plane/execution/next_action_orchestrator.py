"""Mandatory agent-core next-action orchestration scaffold.

The platform must call agent-core's next-action system for every action decision.
Executors are implementation details. They may run deterministic or agentic code,
but they must not choose the next platform action on their own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from agent_core_client.client import AgentCoreClient

NEXT_ACTION_REQUIRED = os.environ.get("AGENT_CORE_NEXT_ACTION_REQUIRED", "true").lower() != "false"
NEXT_ACTION_STRICT = os.environ.get("AGENT_CORE_NEXT_ACTION_STRICT", "false").lower() == "true"


@dataclass
class NextActionRequest:
    session_id: str
    repo_id: str = ""
    task_type: str = "coding"
    current_action: str = ""
    completed_actions: list[str] = field(default_factory=list)
    proposed_action_name: str = ""
    proposed_params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class NextActionDecision:
    allowed: bool
    action_name: str
    params: dict[str, Any]
    reason: str
    recommendation: dict[str, Any] = field(default_factory=dict)
    compatibility_mode: bool = False


class MandatoryNextActionOrchestrator:
    """Small compatibility wrapper around AgentCoreClient.recommend_next().

    Current plan execution can pass a planned step as the proposed action. This
    orchestrator asks agent-core for the next action first, then returns the
    recommended action if present. If agent-core is unavailable, compatibility
    mode can keep existing flows running unless AGENT_CORE_NEXT_ACTION_STRICT is
    enabled.
    """

    def __init__(self, client: AgentCoreClient | None = None, required: bool | None = None, strict: bool | None = None):
        self.client = client
        self.required = NEXT_ACTION_REQUIRED if required is None else required
        self.strict = NEXT_ACTION_STRICT if strict is None else strict

    async def decide(self, request: NextActionRequest) -> NextActionDecision:
        proposed_action = request.proposed_action_name or request.current_action
        proposed_params = dict(request.proposed_params or {})

        if not self.required:
            return NextActionDecision(True, proposed_action, proposed_params, "mandatory next-action gate disabled")

        if self.client is None:
            if self.strict:
                return NextActionDecision(False, proposed_action, proposed_params, "agent-core client is required for next-action decisions")
            return NextActionDecision(True, proposed_action, proposed_params, "agent-core client missing; compatibility mode", compatibility_mode=True)

        try:
            payload = await self.client.recommend_next(
                task_type=request.task_type,
                current_action=request.current_action or proposed_action,
                completed_actions=request.completed_actions,
                session_id=request.session_id,
                repo_id=request.repo_id,
            )
        except Exception as exc:
            if self.strict:
                return NextActionDecision(False, proposed_action, proposed_params, f"agent-core next-action call failed: {exc}")
            return NextActionDecision(True, proposed_action, proposed_params, f"agent-core next-action call failed; compatibility mode: {exc}", compatibility_mode=True)

        recommended_action = payload.get("action_name") or payload.get("next_action") or payload.get("recommended_action") or proposed_action
        recommended_params = payload.get("params") if isinstance(payload.get("params"), dict) else proposed_params
        return NextActionDecision(True, str(recommended_action), dict(recommended_params or {}), "agent-core next-action recommendation received", recommendation=payload)
