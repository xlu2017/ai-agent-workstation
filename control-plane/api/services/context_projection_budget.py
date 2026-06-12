from __future__ import annotations

from dataclasses import dataclass, field

from api.models.session_graph import (
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
    profile: str
    include_selectors: list[ProjectionSelector] = field(default_factory=list)
    exclude_selectors: list[ProjectionSelector] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    rationale: str = ""
    budget_rationale: str = ""


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


def _budget_evidence(profile: str, budget: ContextProjectionBudget, budget_rationale: str) -> list[str]:
    return [
        f"budget_profile:{profile}",
        f"budget_tokens:{budget.max_tokens}",
        f"budget_files:{budget.max_files}",
        f"budget_events:{budget.max_events}",
        f"budget_recency_days:{budget.recency_days}",
        f"budget_rationale:{budget_rationale}",
    ]


def select_context_projection_budget(
    source: SessionRecord,
    target: SessionRecord,
    mount_mode: MountMode,
    user_intent: str,
    *,
    mapping_based: bool = False,
) -> ProjectionBudgetDecision:
    """Select a task-scoped context projection budget for mounted or adapted sessions.

    The budget is intentionally not a proxy for source size. A huge mounted repo under
    a small goal should project only the context that advances the active target.
    Otherwise the mounted session pollutes and dominates the active goal.
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
        profile = "direct_ui_action"
        budget = ContextProjectionBudget(max_tokens=1000, max_files=0, max_events=5, recency_days=1)
        budget_rationale = (
            "1000 tokens because direct UI actions need immediate state, success criteria, "
            "and at most the last 5 events; relevant files are intentionally excluded."
        )
        return ProjectionBudgetDecision(
            profile=profile,
            budget=budget,
            include_selectors=[ProjectionSelector.SUMMARY, ProjectionSelector.SUCCESS_CRITERIA],
            exclude_selectors=[
                ProjectionSelector.RELEVANT_FILES,
                ProjectionSelector.DEPLOYMENT,
                ProjectionSelector.PLUGINS,
                ProjectionSelector.HISTORICAL_NOISE,
            ],
            evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
            rationale=budget_rationale,
            budget_rationale=budget_rationale,
        )

    if _cross_repo_intent(source, target, mount_mode, user_intent):
        profile = "cross_repo_integration"
        budget = ContextProjectionBudget(max_tokens=22000, max_files=32, max_events=160, recency_days=60)
        budget_rationale = (
            "22000 tokens because cross-repo integration must carry selected interface files, "
            "adapter mappings, API contracts, constraints, and recent failures without importing whole histories."
        )
        return ProjectionBudgetDecision(
            profile=profile,
            budget=budget,
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
            evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
            rationale=budget_rationale,
            budget_rationale=budget_rationale,
        )

    if _architecture_intent(user_intent):
        profile = "architecture_planning"
        budget = ContextProjectionBudget(max_tokens=20000, max_files=60, max_events=200, recency_days=90)
        budget_rationale = (
            "20000 tokens because architecture planning needs broad structure, relationships, "
            "interfaces, known paths, and API contracts while still excluding unrelated capability history."
        )
        return ProjectionBudgetDecision(
            profile=profile,
            budget=budget,
            include_selectors=[
                ProjectionSelector.SUMMARY,
                ProjectionSelector.FACETS,
                ProjectionSelector.RELATIONSHIPS,
                ProjectionSelector.INTERFACES,
                ProjectionSelector.KNOWN_PATHS,
                ProjectionSelector.API_CONTRACTS,
            ],
            exclude_selectors=[ProjectionSelector.HISTORICAL_NOISE, ProjectionSelector.UNRELATED_CAPABILITIES],
            evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
            rationale=budget_rationale,
            budget_rationale=budget_rationale,
        )

    if _bug_fix_intent(user_intent):
        profile = "known_repo_bug_fix"
        budget = ContextProjectionBudget(max_tokens=6000, max_files=12, max_events=50, recency_days=30)
        budget_rationale = (
            "6000 tokens because a known-area bug fix should include likely files, commands, "
            "recent failures, and validation criteria, but not the full mounted session."
        )
        return ProjectionBudgetDecision(
            profile=profile,
            budget=budget,
            include_selectors=[
                ProjectionSelector.SUMMARY,
                ProjectionSelector.RELEVANT_FILES,
                ProjectionSelector.SUCCESS_CRITERIA,
                ProjectionSelector.KNOWN_COMMANDS,
            ],
            exclude_selectors=[ProjectionSelector.DEPLOYMENT, ProjectionSelector.PLUGINS, ProjectionSelector.HISTORICAL_NOISE],
            evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
            rationale=budget_rationale,
            budget_rationale=budget_rationale,
        )

    if broad_to_focused:
        profile = "focused_mount_projection"
        budget = ContextProjectionBudget(max_tokens=4000, max_files=12, max_events=50, recency_days=30)
        budget_rationale = (
            "4000 tokens because a broad mounted source under a focused target must expose capabilities, "
            "behaviors, interfaces, and termination conditions without letting the source dominate the active goal."
        )
        return ProjectionBudgetDecision(
            profile=profile,
            budget=budget,
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
            evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
            rationale=budget_rationale,
            budget_rationale=budget_rationale,
        )

    profile = "general_session_context"
    budget = ContextProjectionBudget(max_tokens=12000, max_files=40, max_events=200, recency_days=30)
    budget_rationale = (
        "12000 tokens because general session context needs summaries, facets, and relationships, "
        "but no narrower profile justified a larger or smaller context envelope."
    )
    return ProjectionBudgetDecision(
        profile=profile,
        budget=budget,
        include_selectors=[ProjectionSelector.SUMMARY, ProjectionSelector.FACETS, ProjectionSelector.RELATIONSHIPS],
        exclude_selectors=[ProjectionSelector.HISTORICAL_NOISE],
        evidence=[*common_evidence, *_budget_evidence(profile, budget, budget_rationale)],
        rationale=budget_rationale,
        budget_rationale=budget_rationale,
    )
