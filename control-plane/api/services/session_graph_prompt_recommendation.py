"""Adapter for graph-session prompt routing recommendations from agent-core."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

AGENT_CORE_URL = os.environ.get("AGENT_CORE_URL", "http://localhost:3210").rstrip("/")
AGENT_CORE_TIMEOUT = float(os.environ.get("AGENT_CORE_TIMEOUT", "10"))

PROMPT_ROUTES = {"continue_active", "question_only", "create_child_goal", "create_sibling_goal"}
ROUTE_PROMPT_VISIBLE_ACTIONS = ["session.route_prompt"]


class PromptRoutingUnavailable(RuntimeError):
    """Raised when agent-core cannot provide a valid prompt route."""


@dataclass(frozen=True)
class PromptRouteRecommendation:
    route: str
    reason: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    assistant_response: str = ""
    response_session_kind: str = ""
    narration: str = ""


def _session_context(session: Any, prompt: str) -> dict[str, Any]:
    return {
        "decision_phase": "graph_session_prompt_routing",
        "prompt_kind": "graph_session_followup",
        "visible_actions": ROUTE_PROMPT_VISIBLE_ACTIONS,
        "session_id": session.id,
        "target_session_id": session.id,
        "prompt": prompt,
        "user_prompt": prompt,
        "session_kind": getattr(session.kind, "value", session.kind),
        "session_status": getattr(session.status, "value", session.status),
        "session_title": session.title,
        "has_repo_context": bool(session.metadata.get("repo_session_id")),
        "repo_session_id": session.metadata.get("repo_session_id"),
        "root_session_id": session.root_id or session.id,
    }


def _parse_route_params(params: Any, reason: str, source: str, payload: dict[str, Any]) -> PromptRouteRecommendation | None:
    if not isinstance(params, dict):
        return None
    route = str(params.get("route") or "")
    if route not in PROMPT_ROUTES:
        return None
    route_reason = str(params.get("reason") or reason or "agent-core recommended prompt route")
    assistant_response = str(params.get("assistant_response") or "")
    response_session_kind = str(params.get("response_session_kind") or ("chat" if route == "question_only" else ""))
    narration = str(params.get("narration") or params.get("progress_note") or "")
    return PromptRouteRecommendation(
        route=route,
        reason=route_reason,
        source=source,
        payload=payload,
        assistant_response=assistant_response,
        response_session_kind=response_session_kind,
        narration=narration,
    )


def _parse_next_task_decision(payload: dict[str, Any]) -> PromptRouteRecommendation | None:
    decision = payload.get("next_task_decision")
    if not isinstance(decision, dict):
        # Also accept a direct v0002 response for local tests or proxy shims.
        decision = payload
    if decision.get("task_name") != "session.route_prompt":
        return None
    if decision.get("decision") not in {"execute", "find_out_more"}:
        return None
    return _parse_route_params(
        decision.get("params"),
        str(decision.get("reason") or ""),
        str(payload.get("source") or "agent_core_next_task"),
        payload,
    )


def _parse_legacy_recommendation(payload: dict[str, Any]) -> PromptRouteRecommendation | None:
    recommendation = payload.get("recommendation") or (payload.get("recommendations") or [None])[0]
    if not isinstance(recommendation, dict):
        return None
    if recommendation.get("action_name") != "session.route_prompt":
        return None
    return _parse_route_params(
        recommendation.get("params"),
        str(recommendation.get("rationale") or ""),
        str(payload.get("source") or "agent_core"),
        payload,
    )


def _parse_recommendation(payload: dict[str, Any]) -> PromptRouteRecommendation | None:
    return _parse_next_task_decision(payload) or _parse_legacy_recommendation(payload)


def recommend_graph_prompt_route(session: Any, prompt: str) -> PromptRouteRecommendation:
    """Return the advisory prompt route from a constrained recommend-next pass.

    Graph chat must fail closed when agent-core cannot route the prompt. The
    platform should not silently guess a route when the configured LLM or
    agent-core recommend-next service is unavailable.
    """
    context = _session_context(session, prompt)
    request_body = {
        "task_type": "unknown",
        "current_action": "session.route_prompt",
        "completed_actions": [],
        "visible_actions": ROUTE_PROMPT_VISIBLE_ACTIONS,
        "context": context,
        "session_graph_projection": {
            "active_session": context,
            "routing_options": sorted(PROMPT_ROUTES),
        },
    }
    try:
        response = httpx.post(f"{AGENT_CORE_URL}/actions/recommend-next", json=request_body, timeout=AGENT_CORE_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise PromptRoutingUnavailable(f"agent-core prompt routing unavailable: {exc}") from exc

    parsed = _parse_recommendation(payload)
    if parsed is None:
        raise PromptRoutingUnavailable("agent-core did not return a valid session.route_prompt recommendation")
    return parsed
