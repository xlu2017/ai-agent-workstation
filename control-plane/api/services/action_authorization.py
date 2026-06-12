from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.models.session_graph import ActionStakes, SessionGraphSnapshot, SessionRecord
from api.services.platform_settings import AutomationSettings, get_automation_settings


class ProposedAction(BaseModel):
    """Minimal next-action shape consumed by the authorization gate.

    The LLM/agent-core validator should validate the full schema first. This
    control-plane model intentionally keeps only the fields needed to decide if
    the UI must ask in chat before execution.
    """

    decision: str
    task_name: str
    target_session_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    certainty: float = Field(ge=0, le=1)
    stakes: ActionStakes = ActionStakes.READ_ONLY
    risk: str = "medium"


class ActionAuthorizationContext(BaseModel):
    validation_passed: bool = False
    explicit_user_approval: bool = False
    automation_settings: AutomationSettings | None = None


class ActionAuthorizationResult(BaseModel):
    authorized: bool
    requires_user_confirmation: bool = False
    blocked: bool = False
    reason: str
    required_setting: str | None = None
    warnings: list[str] = Field(default_factory=list)


TASK_AUTOMATION_FEATURES: dict[str, str] = {
    "apply_patch": "auto_apply_patch",
    "edit_file": "auto_apply_patch",
    "create_file": "auto_apply_patch",
    "rename_file": "auto_apply_patch",
    "delete_file": "auto_apply_patch",
    "run_known_tests": "auto_run_tests",
    "run_lint": "auto_run_lint",
    "run_typecheck": "auto_run_typecheck",
    "commit": "auto_commit",
    "push": "auto_push",
    "create_pr": "auto_create_pr",
    "merge_pr": "auto_merge_pr",
    "deploy": "auto_deploy",
    "use_secret": "auto_use_secret",
}

EXTERNAL_SIDE_EFFECT_TASKS = {
    "commit",
    "push",
    "create_pr",
    "merge_pr",
    "deploy",
    "use_secret",
}

DEFAULT_STAKES_THRESHOLDS = {
    ActionStakes.READ_ONLY: 0.55,
    ActionStakes.EXECUTION: 0.75,
    ActionStakes.MODIFICATION: 0.85,
    ActionStakes.EXTERNAL_SIDE_EFFECT: 0.95,
}


def _session_by_id(graph: SessionGraphSnapshot, session_id: str) -> SessionRecord | None:
    for session in graph.sessions:
        if session.id == session_id:
            return session
    return None


def _automation_feature_for(action: ProposedAction) -> str | None:
    if action.task_name in TASK_AUTOMATION_FEATURES:
        return TASK_AUTOMATION_FEATURES[action.task_name]
    if action.stakes == ActionStakes.MODIFICATION:
        return "auto_apply_patch"
    return None


def authorize_action(
    action: ProposedAction,
    graph: SessionGraphSnapshot,
    context: ActionAuthorizationContext | None = None,
) -> ActionAuthorizationResult:
    """Authorize one proposed action against automation settings and session policy.

    This is deliberately separate from validation. A valid action can still be
    unauthorized for automatic execution because the user disabled auto-push,
    validation has not passed, or the target session is private.
    """

    context = context or ActionAuthorizationContext()
    settings = context.automation_settings or get_automation_settings()

    if action.decision != "execute":
        return ActionAuthorizationResult(
            authorized=True,
            reason="Non-execution decisions do not require automatic execution authorization.",
        )

    threshold = settings.certainty_thresholds.get(action.task_name, DEFAULT_STAKES_THRESHOLDS[action.stakes])
    if action.certainty < threshold:
        return ActionAuthorizationResult(
            authorized=False,
            blocked=True,
            reason=f"Certainty {action.certainty} is below required threshold {threshold} for {action.task_name}.",
        )

    feature = _automation_feature_for(action)
    if feature and not getattr(settings, feature) and not context.explicit_user_approval:
        return ActionAuthorizationResult(
            authorized=False,
            requires_user_confirmation=True,
            reason=f"{feature} is disabled. Ask for chat confirmation before executing {action.task_name}.",
            required_setting=feature,
        )

    if action.task_name in EXTERNAL_SIDE_EFFECT_TASKS or action.stakes == ActionStakes.EXTERNAL_SIDE_EFFECT:
        if settings.require_validation_before_external_side_effect and not context.validation_passed:
            return ActionAuthorizationResult(
                authorized=False,
                blocked=True,
                reason="External side effects require successful validation before automatic execution.",
            )

    warnings: list[str] = []
    for session_id in action.target_session_ids:
        session = _session_by_id(graph, session_id)
        if session is None:
            return ActionAuthorizationResult(
                authorized=False,
                blocked=True,
                reason=f"Target session {session_id} does not exist.",
            )
        if (
            settings.require_private_session_confirmation
            and session.policy.visibility == "private"
            and not context.explicit_user_approval
        ):
            return ActionAuthorizationResult(
                authorized=False,
                requires_user_confirmation=True,
                reason=f"Target session {session_id} is private. Ask for chat confirmation before execution.",
            )
        if session.policy.security_constraints:
            warnings.append(
                f"Target session {session_id} has security constraints: {', '.join(session.policy.security_constraints)}"
            )

    return ActionAuthorizationResult(
        authorized=True,
        reason="Action is authorized by current automation settings and session policy.",
        warnings=warnings,
    )
