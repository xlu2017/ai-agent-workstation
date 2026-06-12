from __future__ import annotations

from dataclasses import dataclass, field

from api.models.session_graph import (
    ContextBudgetProfile,
    ContextProjectionBudget,
    MountMode,
    ProjectionSelector,
    SessionKind,
    SessionRecord,
)


BROAD_SESSION_KINDS = {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER}
FOCUSED_SESSION_KINDS = {SessionKind.GOAL, SessionKind.WORK, SessionKind.QUESTION}


@dataclass(frozen=True)
class ProjectionBudgetDecision:
    budget: ContextProjectionBudget
    profile: ContextBudgetProfile
    include_selectors: list[ProjectionSelector] = field(default_factory=list)
    exclude_selectors: list[ProjectionSelector] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    rationale: str = ""


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _broad_source_under_focused_target(source: SessionRecord, target: SessionRecord) -> bool:
    return source.kind in BROAD_SESSION_KINDS and target.kind in FOCUSED_SESSION_KINDS


def _direct_ui_action_intent(user_intent: str, target: SessionRecord) -> bool:
    return target.kind == SessionKind.RUNTIME or _has_any(
        user_intent,
        (
            "click",
            "press",
            "open the",
            "direct ui",
            "desktop",
            "browser",
            "button",
            "control",
            "remote desktop",
        ),
    )


def _bug_fix_intent(user_intent: str) -> bool:
    return _has_any(user_intent, ("bug", "fix", "failing", "failure", "error", "test", "regression"))


def _architecture_intent(user_intent: str) -> bool:
    return _has_any(
        user_intent,
        (
            "architecture",
            "architect",
            "design",
            "plan",
            "scaffold",
            "session model",
            "system",
            "refactor",
            "workflow",
        ),
    )


def _cross_repo_intent(source: SessionRecord, target: SessionRecord, mount_mode: MountMode, user_intent: str) -> bool:
    if mount_mode in {MountMode.COMPONENT, MountMode.DEPENDENCY, MountMode.VENDOR, MountMode.PORT, MountMode.WRAP}:
        return True
    if source.kind in BROAD_SESSION_KINDS and target.kind in {SessionKind.APP, SessionKind.GOAL, SessionKind.WORK}:
        return _has_any(
            user_intent,
            (
                "integrate",
                "adapter",
                "map",
                "api",
                "interface",
                "cross-repo",
                "repo into",
                "port",
                "wrap",
                "vendor",
            ),
        )
    return False


def select_context_projection_budget(
    source: SessionRecord,
    target: SessionRecord,
    mount_mode: MountMode,
    user_intent: str,
    *,
    mapping_based: bool = False,
) -> ProjectionBudgetDecision:
    """Select a context projection budget for mounted or adapted sessions.

    The selected budget is intentionally not a proxy for source size. It is a task-scoped
    projection envelope. A huge mounted repo under a small goal should project only the
    context that advances the active target, otherwise the mounted session pollutes and
    dominates the active goal.
    """
    broad_to_focused = _broad_source_under_focused_target(source, target)
    common_evidence = [
        f"source_kind:{source.kind.value}",
        f"target_kind:{target.kind.value}",
        f"mount_mode:{mount_mode.value}",
    ]
    if mapping_based:
        common_evidence.append("mapping_based:true")
    if broad_to_focused:
        common_evidence.append("dominance_guard:broad_source_under_focused_target")

    if _direct_ui_action_intent(user_intent, target):
        return ProjectionBudgetDecision(
            profile=ContextBudgetProfile.DIRECT_UI_ACTION,
            budget=ContextProjectionBudget(
                max_tokens=1000,
                max_files=0,
                max_events=5,
                recency_days=1,
                profile=ContextBudgetProfile.DIRECT_UI_ACTION,
                notes=["Direct UI actions should use ambient state and recent events, not repository context."],
            ),
            include_selectors=[ProjectionSelector.SUMMARY, ProjectionSelector.SUCCESS_CRITERIA],
            exclude_selectors=[
                ProjectionSelector.RELEVANT_FILES,
                ProjectionSelector.DEPLOYMENT,
                ProjectionSelector.PLUGINS,
                ProjectionSelector.HISTORICAL_NOISE,
            ],
            evidence=[*common_evidence, "budget_profile:direct_ui_action"],
            rationale="Project only immediate UI state and recent session events for the active action.",
        )

    if _cross_repo_intent(source, target, mount_mode, user_intent):
        return ProjectionBudgetDecision(
            profile=ContextBudgetProfile.CROSS_REPO_INTEGRATION,
            budget=ContextProjectionBudget(
                max_tokens=22000,
                max_files=32,
                max_events=160,
                recency_days=60,
                profile=ContextBudgetProfile.CROSS_REPO_INTEGRATION,
                notes=[
                    "Use selected interface files, adapter mappings, and recent failures instead of whole-repo history.",
                    "Mounted sessions remain subordinate to the active goal even when their source is large.",
                ],
            ),
            include_selectors=[
                ProjectionSelector.ADAPTER_MAPPINGS,
                ProjectionSelector.INTERFACES,
                ProjectionSelector.API_CONTRACTS,
                ProjectionSelector.RELEVANT_FILES,
                ProjectionSelector.SECURITY_CONSTRAINTS,
            ],
            exclude_selectors=[
                ProjectionSelector.UNRELATED_UI,
                ProjectionSelector.DEPLOYMENT,
                ProjectionSelector.PLUGINS,
                ProjectionSelector.HISTORICAL_NOISE,
                ProjectionSelector.UNRELATED_CAPABILITIES,
            ],
            evidence=[*common_evidence, "budget_profile:cross_repo_integration"],
            rationale="Project interface and adapter context for cross-session integration without importing source history wholesale.",
        )

    if _architecture_intent(user_intent):
        return ProjectionBudgetDecision(
            profile=ContextBudgetProfile.ARCHITECTURE_PLANNING,
            budget=ContextProjectionBudget(
                max_tokens=20000,
                max_files=60,
                max_events=200,
                recency_days=90,
                profile=ContextBudgetProfile.ARCHITECTURE_PLANNING,
                notes=["Architecture work may inspect broad structure but should still exclude unrelated mounted-session noise."],
            ),
            include_selectors=[
                ProjectionSelector.SUMMARY,
                ProjectionSelector.FACETS,
                ProjectionSelector.RELATIONSHIPS,
                ProjectionSelector.INTERFACES,
                ProjectionSelector.KNOWN_PATHS,
                ProjectionSelector.API_CONTRACTS,
            ],
            exclude_selectors=[ProjectionSelector.HISTORICAL_NOISE, ProjectionSelector.UNRELATED_CAPABILITIES],
            evidence=[*common_evidence, "budget_profile:architecture_planning"],
            rationale="Provide enough structure for planning while keeping unrelated histories out of the active goal.",
        )

    if _bug_fix_intent(user_intent):
        return ProjectionBudgetDecision(
            profile=ContextBudgetProfile.KNOWN_REPO_BUG_FIX,
            budget=ContextProjectionBudget(
                max_tokens=6000,
                max_files=12,
                max_events=50,
                recency_days=30,
                profile=ContextBudgetProfile.KNOWN_REPO_BUG_FIX,
                notes=["Bug fixes should favor known files, recent failures, and validation evidence."],
            ),
            include_selectors=[
                ProjectionSelector.SUMMARY,
                ProjectionSelector.RELEVANT_FILES,
                ProjectionSelector.SUCCESS_CRITERIA,
                ProjectionSelector.KNOWN_COMMANDS,
            ],
            exclude_selectors=[ProjectionSelector.DEPLOYMENT, ProjectionSelector.PLUGINS, ProjectionSelector.HISTORICAL_NOISE],
            evidence=[*common_evidence, "budget_profile:known_repo_bug_fix"],
            rationale="Project a focused bug-fix envelope: likely files, commands, recent failures, and validation criteria.",
        )

    if broad_to_focused:
        return ProjectionBudgetDecision(
            profile=ContextBudgetProfile.FOCUSED_MOUNT_PROJECTION,
            budget=ContextProjectionBudget(
                max_tokens=4000,
                max_files=12,
                max_events=50,
                recency_days=30,
                profile=ContextBudgetProfile.FOCUSED_MOUNT_PROJECTION,
                notes=[
                    "Do not let the mounted session dominate the active goal.",
                    "Only project context that can solve the current target.",
                ],
            ),
            include_selectors=[
                ProjectionSelector.CAPABILITIES,
                ProjectionSelector.BEHAVIORS,
                ProjectionSelector.INTERFACES,
                ProjectionSelector.TERMINATION_CONDITIONS,
            ],
            exclude_selectors=[
                ProjectionSelector.UNRELATED_UI,
                ProjectionSelector.DEPLOYMENT,
                ProjectionSelector.PLUGINS,
                ProjectionSelector.HISTORICAL_NOISE,
                ProjectionSelector.UNRELATED_CAPABILITIES,
            ],
            evidence=[*common_evidence, "budget_profile:focused_mount_projection"],
            rationale="Project a smaller source view so the mounted session supports rather than replaces the active goal.",
        )

    return ProjectionBudgetDecision(
        profile=ContextBudgetProfile.GENERAL_SESSION_CONTEXT,
        budget=ContextProjectionBudget(
            max_tokens=12000,
            max_files=40,
            max_events=200,
            recency_days=30,
            profile=ContextBudgetProfile.GENERAL_SESSION_CONTEXT,
            notes=["General session context for same-scale or low-risk graph composition."],
        ),
        include_selectors=[ProjectionSelector.SUMMARY, ProjectionSelector.FACETS, ProjectionSelector.RELATIONSHIPS],
        exclude_selectors=[ProjectionSelector.HISTORICAL_NOISE],
        evidence=[*common_evidence, "budget_profile:general_session_context"],
        rationale="Project general session context because no narrower task-specific profile matched.",
    )
