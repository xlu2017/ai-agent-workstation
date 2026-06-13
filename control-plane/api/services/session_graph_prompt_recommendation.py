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


@dataclass(frozen=True)
class PromptRouteRecommendation:
    route: str
    reason: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)


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


def _parse_recommendation(payload: dict[str, Any]) -> PromptRouteRecommendation | None:
    recommendation = payload.get("recommendation") or (payload.get("recommendations") or [None])[0]
    if not isinstance(recommendation, dict):
        return None
    if recommendation.get("action_name") != "session.route_prompt":
        return None
    params = recommendation.get("params")
    if not isinstance(params, dict):
        return None
    route = str(params.get("route") or "")
    if route not in PROMPT_ROUTES:
        return None
    reason = str(params.get("reason") or recommendation.get("rationale") or "agent-core recommended prompt route")
    return PromptRouteRecommendation(route=route, reason=reason, source=str(payload.get("source") or "agent_core"), payload=payload)


def recommend_graph_prompt_route(session: Any, prompt: str) -> PromptRouteRecommendation:
    """Return the advisory prompt route from a constrained recommend-next pass.

    The platform chooses visible_actions because this endpoint is known to be a
    graph-session prompt-routing phase. The user prompt never determines the
    visible action set.
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
        parsed = _parse_recommendation(response.json())
        if parsed is not None:
            return parsed
        return PromptRouteRecommendation("question_only", "agent-core did not return a valid session.route_prompt recommendation", "invalid_agent_core_response", {})
    except Exception as exc:
        return PromptRouteRecommendation("question_only", f"agent-core prompt routing unavailable: {exc}", "agent_core_unavailable", {})
