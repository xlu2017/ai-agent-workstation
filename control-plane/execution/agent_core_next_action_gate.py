"""
Mandatory agent-core next-action gate.

Intent:
- Every action execution cycle must pass through agent-core next-action recommendation.
- Execution adapters do not decide what to do next; they only execute the action selected by the platform after agent-core advice, platform validation, and authorization.
- Deterministic shortcuts are allowed only as executors for an action that has already passed this gate.
- Long-horizon work is achieved by repeating observe -> ask agent-core -> validate -> authorize -> execute -> record outcome.

This scaffold is intentionally conservative. It can annotate existing plan steps with
agent-core next-action evidence without breaking the current plan executor. Later it
should become the only source of the next action in open-ended sessions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from agent_core_client.client import AgentCoreClient

AGENT_CORE_NEXT_ACTION_REQUIRED = (
    os.environ.get("AGENT_CORE_NEXT_ACTION_REQUIRED", "true").lower() != "false"
)
AGENT_CORE_NEXT_ACTION_FAIL_CLOSED = (
    os.environ.get("AGENT_CORE_NEXT_ACTION_FAIL_CLOSED", "false").lower() == "true"
)


@dataclass
class NextActionGateInput:
    session_id: str
    repo_id: str = ""
    task_type: str = "coding"
    current_action: str = ""
    completed_actions: list[str] = field(default_factory=list)
    proposed_action_name: str = ""
    proposed_params: dict[str, Any] = field(default_factory=dict)
    recent_outcomes: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class NextActionGateResult:
    allowed: bool
    reason: str
    action_name: str
    params: dict[str, Any] = field(default_factory=dict)
    agent_core_payload: dict[str, Any] = field(default_factory=dict)
    advisory_only: bool = True
    fail_open_used: bool = False


class AgentCoreNextActionGate:
    """Mandatory adapter around agent-core next-action recommendation."""

    def __init__(
        self,
        client: AgentCoreClient | None = None,
        required: bool | None = None,
        fail_closed: bool | None = None,
    ):
        self.client = client
        self.required = AGENT_CORE_NEXT_ACTION_REQUIRED if required is None else required
        self.fail_closed = AGENT_CORE_NEXT_ACTION_FAIL_CLOSED if fail_closed is None else fail_closed

    async def decide(self, gate_input: NextActionGateInput) -> NextActionGateResult:
        """Ask agent-core for next-action advice before an action is executed.

        Current compatibility behavior:
        - If agent-core is reachable, attach its recommendation evidence.
        - If it recommends a concrete action name, prefer that over the proposed step.
        - If agent-core is unavailable and fail_closed=false, allow the proposed step but mark fail_open_used.
        - If fail_closed=true, block execution when agent-core advice cannot be obtained.
        """

        proposed = gate_input.proposed_action_name or gate_input.current_action
        if not self.required:
            return NextActionGateResult(
                allowed=True,
                reason="agent-core next-action gate disabled by configuration",
                action_name=proposed,
                params=dict(gate_input.proposed_params),
            )

        if self.client is None:
            if self.fail_closed:
                return NextActionGateResult(
                    allowed=False,
                    reason="agent-core next-action gate is required but no client is configured",
                    action_name=proposed,
                    params=dict(gate_input.proposed_params),
                )
            return NextActionGateResult(
                allowed=True,
                reason="agent-core next-action client missing; compatibility fail-open used",
                action_name=proposed,
                params=dict(gate_input.proposed_params),
                fail_open_used=True,
            )

        try:
            payload = await self.client.recommend_next(
                task_type=gate_input.task_type,
                current_action=gate_input.current_action or proposed,
                completed_actions=gate_input.completed_actions,
                session_id=gate_input.session_id,
                repo_id=gate_input.repo_id,
            )
        except Exception as exc:
            if self.fail_closed:
                return NextActionGateResult(
                    allowed=False,
                    reason=f"agent-core next-action recommendation failed: {exc}",
                    action_name=proposed,
                    params=dict(gate_input.proposed_params),
                )
            return NextActionGateResult(
                allowed=True,
                reason=f"agent-core next-action recommendation failed; compatibility fail-open used: {exc}",
                action_name=proposed,
                params=dict(gate_input.proposed_params),
                fail_open_used=True,
            )

        recommended_action = (
            payload.get("action_name")
            or payload.get("next_action")
            or payload.get("recommended_action")
            or proposed
        )
        recommended_params = payload.get("params") if isinstance(payload.get("params"), dict) else gate_input.proposed_params

        return NextActionGateResult(
            allowed=True,
            reason="agent-core next-action recommendation obtained",
            action_name=str(recommended_action),
            params=dict(recommended_params or {}),
            agent_core_payload=payload,
            advisory_only=bool(payload.get("advisory_only", True)),
        )
