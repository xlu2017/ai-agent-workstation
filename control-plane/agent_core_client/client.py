"""
agent-core HTTP client for jubilant-goggles.

agent-core is an advisory service for memory, context, action knowledge,
schema validation, and next-action recommendations.

This client may call agent-core for:
  POST /actions/recommend-next — advisory single next-action recommendation
  POST /actions/validate       — action contract validation
  GET  /actions                — fetch action catalog
  POST /memory/search          — search memories
  POST /context/search         — search context
  POST /actions/outcome        — record execution outcomes

This client must not ask agent-core to:
  generate execution plans
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
        visible_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get an advisory single next-action recommendation.

        visible_actions is selected by the platform workflow phase, not inferred
        from the user prompt. It constrains which actions agent-core may choose.
        """
        context: dict[str, Any] = {"session_id": session_id, "repo_id": repo_id}
        if visible_actions:
            context["visible_actions"] = visible_actions
        if ambient_context:
            context["ambient_context"] = ambient_context
        if suggested_plan:
            # This is accepted only for prompt-context compatibility. Execution
            # flows do not pass a plan here; recommend-next remains single-action.
            context["suggested_plan"] = suggested_plan
        payload = {
            "task_type": task_type,
            "current_action": current_action,
            "completed_actions": completed_actions,
            "context": context,
        }
        if visible_actions:
            payload["visible_actions"] = visible_actions
        resp = await self._client.post("/actions/recommend-next", json=payload)
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
