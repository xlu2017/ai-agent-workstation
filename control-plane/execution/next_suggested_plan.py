from __future__ import annotations

from typing import Any


class NextSuggestedPlanError(ValueError):
    """Raised when a recommend-next payload cannot be converted to a plan."""


def next_suggestion_to_plan(
    *,
    prompt: str,
    recommendation: dict[str, Any],
    mode_preference: str = "finite",
) -> dict[str, Any]:
    """Convert an advisory recommend-next response into an executable plan shell.

    jubilant-goggles no longer calls agent-core's plan endpoint here. Instead,
    recommend-next is the advisory source of truth. This adapter keeps the
    existing workflow executor contract by wrapping the recommended next action
    as a one-step, platform-validated plan.
    """

    raw = _recommendation_payload(recommendation)
    explicit_plan = _extract_explicit_next_plan(raw)
    if explicit_plan is not None:
        return _normalize_plan(explicit_plan, prompt=prompt, mode_preference=mode_preference, source_payload=raw)

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
        "next_suggested_plan": raw,
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


def _extract_explicit_next_plan(raw: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("next_suggested_plan", "suggested_plan", "plan"):
        value = raw.get(key)
        if isinstance(value, dict) and isinstance(value.get("steps"), list) and value["steps"]:
            return value
    return None


def _normalize_plan(
    plan: dict[str, Any],
    *,
    prompt: str,
    mode_preference: str,
    source_payload: dict[str, Any],
) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise NextSuggestedPlanError("next suggested plan must include at least one step")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise NextSuggestedPlanError(f"next suggested plan step {index} must be an object")
        action_name = str(step.get("action_name") or step.get("name") or "").strip()
        if not action_name:
            raise NextSuggestedPlanError(f"next suggested plan step {index} is missing action_name")
        step["action_name"] = action_name
        if "params" not in step:
            step["params"] = step.get("parameters") or {}
        if not isinstance(step["params"], dict):
            raise NextSuggestedPlanError(f"next suggested plan step {index} params must be an object")
        step.setdefault("source", "next_suggested_plan")
    return {
        **plan,
        "mode": plan.get("mode") or mode_preference or "finite",
        "goal": plan.get("goal") or prompt,
        "source": "next_suggested_plan",
        "advisory_only": True,
        "requires_platform_validation": True,
        "next_suggested_plan": source_payload,
        "steps": steps,
    }


def _extract_action(raw: dict[str, Any]) -> dict[str, Any]:
    for key in ("next_action", "suggested_action", "action"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"action_name": value, "params": {}}
    raise NextSuggestedPlanError("recommend-next response did not include next_action, suggested_action, or action")
