"""
agent-core HTTP client for jubilant-goggles.

Calls agent-core for:
  POST /actions/plan          — generate an advisory plan
  POST /actions/validate-plan — deterministic plan validation
  POST /actions/outcome       — record execution outcomes
  POST /actions/recommend-next — stepwise next-action recommendation
  GET  /actions               — fetch action catalog
  POST /memory/search         — search memories
  POST /context/search        — search context

Does NOT ask agent-core to:
  execute, schedule, pause, cancel, commit, create worktrees/branches/PRs
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
    memories: list[dict[str, Any]] = field(default_factory=list)
    context_summaries: list[dict[str, Any]] = field(default_factory=list)
    recent_outcomes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OutcomeRecord:
    session_id: str
    action_name: str
    params: dict[str, Any]
    status: str  # succeeded, failed, skipped
    output: dict[str, Any]
    duration_ms: int
    executor: str
    rationale: str = ""
    error: str = ""
    files_touched: list[str] = field(default_factory=list)
    test_result: str = ""


class AgentCoreClient:
    """HTTP client for agent-core API."""

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
        """GET /actions — fetch the action catalog."""
        resp = await self._client.get("/actions")
        resp.raise_for_status()
        return resp.json()

    async def plan(self, request: PlanRequest) -> dict[str, Any]:
        """POST /actions/plan — generate an LLM-first advisory plan."""
        payload = {
            "session_id": request.session_id,
            "repo_id": request.repo_id,
            "prompt": request.prompt,
            "allowed_actions": request.allowed_actions,
            "mode_preference": request.mode_preference,
        }
        if request.memories:
            payload["memories"] = request.memories
        if request.context_summaries:
            payload["context_summaries"] = request.context_summaries
        if request.recent_outcomes:
            payload["recent_outcomes"] = request.recent_outcomes
        resp = await self._client.post("/actions/plan", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def validate_plan(
        self,
        allowed_actions: list[str],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /actions/validate-plan — deterministic validation."""
        resp = await self._client.post(
            "/actions/validate-plan",
            json={"allowed_actions": allowed_actions, "plan": plan},
        )
        resp.raise_for_status()
        return resp.json()

    async def record_outcome(self, outcome: OutcomeRecord) -> dict[str, Any]:
        """POST /actions/outcome — record what was actually executed."""
        payload = {
            "session_id": outcome.session_id,
            "action_name": outcome.action_name,
            "params": outcome.params,
            "status": outcome.status,
            "output": outcome.output,
            "duration_ms": outcome.duration_ms,
            "executor": outcome.executor,
        }
        if outcome.rationale:
            payload["rationale"] = outcome.rationale
        if outcome.error:
            payload["error"] = outcome.error
        if outcome.files_touched:
            payload["files_touched"] = outcome.files_touched
        if outcome.test_result:
            payload["test_result"] = outcome.test_result
        resp = await self._client.post("/actions/outcome", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def recommend_next(
        self,
        task_type: str,
        current_action: str,
        completed_actions: list[str],
        session_id: str = "",
        repo_id: str = "",
    ) -> dict[str, Any]:
        """POST /actions/recommend-next — stepwise recommendation."""
        resp = await self._client.post(
            "/actions/recommend-next",
            json={
                "task_type": task_type,
                "current_action": current_action,
                "completed_actions": completed_actions,
                "context": {"session_id": session_id, "repo_id": repo_id},
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def search_memory(
        self, query: str, session_id: str = "", limit: int = 10
    ) -> dict[str, Any]:
        """POST /memory/search — search memories in agent-core.

        agent-core scopes memory with scope/scope_id rather than a top-level
        session_id field. Passing session_id directly would either fail schema
        parsing or produce an unscoped search depending on server strictness.
        """
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if session_id:
            payload["scope"] = "session"
            payload["scope_id"] = session_id

        resp = await self._client.post("/memory/search", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()
