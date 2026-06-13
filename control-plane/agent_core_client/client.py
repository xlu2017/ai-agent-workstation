"""
agent-core HTTP client for jubilant-goggles.

agent-core is an advisory service for memory, context, action knowledge,
schema validation, planning, and next-action recommendations.

This client may call agent-core for:
  POST /actions/plan           — generate an advisory plan
  POST /actions/validate-plan  — deterministic advisory plan validation
  POST /actions/recommend-next — advisory next-action recommendation
  POST /actions/validate       — action contract validation
  GET  /actions                — fetch action catalog
  POST /memory/search          — search memories
  POST /context/search         — search context

This client must not ask agent-core to:
  execute actions
  schedule sessions
  pause or cancel sessions
  create worktrees, branches, commits, pushes, deploys, or PRs
  perform runtime authorization

Every response from agent-core must be treated as advisory. jubilant-goggles
must still perform runtime policy checks, approval checks, path/command guards,
executor authorization, and timeline/audit recording before doing anything real.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

AGENT_CORE_URL = os.environ.get("AGENT_CORE_URL", "http://localhost:3210")
AGENT_CORE_TIMEOUT = float(os.environ.get("AGENT_CORE_TIMEOUT", "30"))


@dataclass
class PlanRequest:
    session_id: str
    repo_id: str
    prompt: str
    allowed_actions: list[str]
    mode_preference: str = "finite"
    max_iterations: int | None = None
    recent_memories: list[dict[str, Any]] = field(default_factory=list)
    context_summaries: list[str] = field(default_factory=list)
    recent_action_outcomes: list[dict[str, Any]] = field(default_factory=list)
    ambient_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomeRecord:
    """Outcome record forwarded to agent-core for trace/memory integration."""

    session_id: str
    action_name: str
    params: dict[str, Any]
    status: str  # succeeded | failed | blocked | skipped
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    executor: str = ""
    rationale: str = ""
    error: str = ""
    files_touched: list[str] = field(default_factory=list)


class AgentCoreClient:
    """HTTP client for advisory agent-core APIs."""

    def __init__(
        self,
        base_url: str = AGENT_CORE_URL,
        timeout: float = AGENT_CORE_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def get_actions(self) -> dict[str, Any]:
        """Fetch advisory action catalog from agent-core."""
        resp = await self._client.get("/actions")
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def plan(self, request: PlanRequest) -> dict[str, Any]:
        """Generate an advisory plan. The plan is not authorization."""
        payload: dict[str, Any] = {
            "session_id": request.session_id,
            "repo_id": request.repo_id,
            "prompt": request.prompt,
            "allowed_actions": request.allowed_actions,
            "mode_preference": request.mode_preference,
        }
        if request.max_iterations is not None:
            payload["max_iterations"] = request.max_iterations
        if request.recent_memories:
            payload["recent_memories"] = request.recent_memories
        if request.context_summaries:
            payload["context_summaries"] = request.context_summaries
        if request.recent_action_outcomes:
            payload["recent_action_outcomes"] = request.recent_action_outcomes
        if request.ambient_context:
            payload["ambient_context"] = request.ambient_context
        resp = await self._client.post("/actions/plan", json=payload)
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def validate_plan(
        self,
        allowed_actions: list[str],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate plan shape and visible action membership only."""
        resp = await self._client.post(
            "/actions/validate-plan",
            json={"allowed_actions": allowed_actions, "plan": plan},
        )
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def validate_action(
        self,
        action_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate an action contract. This does not authorize execution."""
        resp = await self._client.post(
            "/actions/validate",
            json={"action_name": action_name, "params": params},
        )
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def recommend_next(
        self,
        task_type: str,
        current_action: str,
        completed_actions: list[str],
        session_id: str = "",
        repo_id: str = "",
        ambient_context: dict[str, Any] | None = None,
        suggested_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get an advisory next-action recommendation."""
        context: dict[str, Any] = {"session_id": session_id, "repo_id": repo_id}
        if ambient_context:
            context["ambient_context"] = ambient_context
        if suggested_plan:
            context["suggested_plan"] = suggested_plan
        resp = await self._client.post(
            "/actions/recommend-next",
            json={
                "task_type": task_type,
                "current_action": current_action,
                "completed_actions": completed_actions,
                "context": context,
            },
        )
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def search_memory(
        self, query: str, session_id: str = "", limit: int = 10
    ) -> dict[str, Any]:
        """Search memories in agent-core using its scope/scope_id contract."""
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if session_id:
            payload["scope"] = "session"
            payload["scope_id"] = session_id

        resp = await self._client.post("/memory/search", json=payload)
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def record_outcome(self, outcome: OutcomeRecord) -> dict[str, Any]:
        """Forward an action outcome to agent-core."""
        payload = {
            "session_id": outcome.session_id,
            "action_name": outcome.action_name,
            "params": outcome.params,
            "status": outcome.status,
            "output": outcome.output,
            "duration_ms": outcome.duration_ms,
            "executor": outcome.executor or "jubilant-goggles",
            "rationale": outcome.rationale,
            "error": outcome.error,
            "files_touched": outcome.files_touched,
        }
        resp = await self._client.post("/actions/outcome", json=payload)
        resp.raise_for_status()
        return self._mark_advisory(resp.json())

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _mark_advisory(payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("advisory_only", True)
        payload.setdefault("requires_platform_validation", True)
        return payload
