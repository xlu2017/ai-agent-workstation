from __future__ import annotations

from typing import Any


class NextSuggestedPlanError(ValueError):
    """Raised when a recommend-next payload cannot be converted to one executable action."""


class NextSuggestedStop(NextSuggestedPlanError):
    """Raised when recommend-next deliberately returns a terminal stop decision."""

    def __init__(self, reason: str):
        super().__init__(reason or "recommend-next returned stop")
        self.reason = reason or "recommend-next returned stop"


def next_suggestion_to_plan(
    *,
    prompt: str,
    recommendation: dict[str, Any],
    mode_preference: str = "finite",
) -> dict[str, Any]:
    """Wrap a single recommend-next action in the executor's one-step plan shell.

    recommend-next is intentionally a single-action advisory interface. The
    returned object is called a plan only to preserve the existing workflow
    executor contract, which consumes ``plan.steps``. This adapter rejects
    multi-step plan-shaped payloads rather than treating recommend-next as a
    planning endpoint.
    """

    raw = _recommendation_payload(recommendation)
    _reject_plan_shaped_payload(raw)
    if raw.get("decision") == "stop":
        raise NextSuggestedStop(str(raw.get("reason") or raw.get("progress_note") or "recommend-next returned stop"))

    action = _extract_action(raw)
    action_name = str(action.get("action_name") or action.get("name") or "").strip()
    if not action_name:
        raise NextSuggestedPlanError("recommend-next response did not include an action_name or task_name")

    params = action.get("params") or action.get("parameters") or {}
    if not isinstance(params, dict):
        raise NextSuggestedPlanError("recommend-next action params must be an object")

    rationale = action.get("rationale") or raw.get("rationale") or raw.get("reason") or "Recommended by next-action advisor."
    return {
        "mode": mode_preference or "finite",
        "goal": prompt,
        "source": "next_suggested_plan",
        "advisory_only": True,
        "requires_platform_validation": True,
        "next_suggested_action": raw,
        "steps": [
            {
                "action_name": action_name,
                "params": params,
                "rationale": str(rationale),
                "source": "next_suggested_plan",
            }
        ],
    }


def _recommendation_payload(recommendation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recommendation, dict):
        raise NextSuggestedPlanError("recommend-next response must be an object")

    next_task_decision = recommendation.get("next_task_decision")
    legacy_recommendation = recommendation.get("recommendation")

    if isinstance(next_task_decision, dict):
        if next_task_decision.get("decision") == "stop" or not isinstance(legacy_recommendation, dict):
            return next_task_decision

    if isinstance(legacy_recommendation, dict):
        return legacy_recommendation

    return recommendation


def _reject_plan_shaped_payload(raw: dict[str, Any]) -> None:
    for key in ("next_suggested_plan", "suggested_plan", "plan", "steps"):
        value = raw.get(key)
        if value:
            raise NextSuggestedPlanError(
                f"recommend-next must suggest exactly one action; plan-shaped field '{key}' is not supported"
            )


def _extract_action(raw: dict[str, Any]) -> dict[str, Any]:
    task_name = raw.get("task_name")
    if isinstance(task_name, str) and task_name.strip():
        return {"action_name": task_name, "params": raw.get("params") or {}}

    for key in ("next_action", "suggested_action", "action"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"action_name": value, "params": {}}
    raise NextSuggestedPlanError("recommend-next response did not include next_action, suggested_action, action, or task_name")
