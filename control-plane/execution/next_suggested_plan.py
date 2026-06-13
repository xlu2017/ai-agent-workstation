from __future__ import annotations

from typing import Any


class NextSuggestedPlanError(ValueError):
    """Raised when a recommend-next payload cannot be converted to one executable action."""


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
    action = _extract_action(raw)
    action_name = str(action.get("action_name") or action.get("name") or "").strip()
    if not action_name:
        raise NextSuggestedPlanError("recommend-next response did not include an action_name")

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
    nested = recommendation.get("recommendation")
    if isinstance(nested, dict):
        return nested
    return recommendation


def _reject_plan_shaped_payload(raw: dict[str, Any]) -> None:
    for key in ("next_suggested_plan", "suggested_plan", "plan", "steps"):
        value = raw.get(key)
        if value:
            raise NextSuggestedPlanError(
                f"recommend-next must suggest exactly one action; plan-shaped field '{key}' is not supported"
            )


def _extract_action(raw: dict[str, Any]) -> dict[str, Any]:
    for key in ("next_action", "suggested_action", "action"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"action_name": value, "params": {}}
    raise NextSuggestedPlanError("recommend-next response did not include next_action, suggested_action, or action")
