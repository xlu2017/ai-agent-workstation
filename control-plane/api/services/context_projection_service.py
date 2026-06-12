from __future__ import annotations

from api.models.session_graph import (
    AdapterMapping,
    ContextProjection,
    MountSessionRequest,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
    SessionKind,
    SessionRecord,
)
from api.services.context_projection_budget import select_context_projection_budget


def generate_budgeted_context_projection(
    source: SessionRecord,
    target: SessionRecord,
    request: MountSessionRequest,
    mappings: list[AdapterMapping] | None = None,
) -> ContextProjection:
    """Generate a task-scoped projection that uses a dynamic budget profile.

    This is the budgeted projection scaffold for the SessionAdapter Engine. The existing
    mount path can call this once the API schema and UI are ready to display named
    budget profiles. Until then, the selected profile is carried as projection evidence.
    """
    broad_source = source.kind in {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER}
    focused_target = target.kind in {SessionKind.GOAL, SessionKind.WORK, SessionKind.QUESTION}
    mapping_based = bool(mappings)
    budget_decision = select_context_projection_budget(
        source,
        target,
        request.mount_mode,
        request.user_intent,
        mapping_based=mapping_based,
    )

    include_selectors = [ProjectionSelector.ADAPTER_MAPPINGS, ProjectionSelector.CAPABILITIES] if mapping_based else []
    include_selectors.extend(budget_decision.include_selectors)
    if broad_source and focused_target and not budget_decision.include_selectors:
        include_selectors.extend([
            ProjectionSelector.CAPABILITIES,
            ProjectionSelector.BEHAVIORS,
            ProjectionSelector.INTERFACES,
            ProjectionSelector.TERMINATION_CONDITIONS,
        ])
    elif not budget_decision.include_selectors:
        include_selectors.extend([ProjectionSelector.SUMMARY, ProjectionSelector.FACETS, ProjectionSelector.RELATIONSHIPS])

    exclude_selectors = list(budget_decision.exclude_selectors)
    if broad_source and focused_target:
        exclude_selectors.extend([
            ProjectionSelector.UNRELATED_UI,
            ProjectionSelector.DEPLOYMENT,
            ProjectionSelector.PLUGINS,
            ProjectionSelector.HISTORICAL_NOISE,
            ProjectionSelector.UNRELATED_CAPABILITIES,
        ])

    evidence = [
        f"source:{source.id}:{source.kind.value}",
        f"target:{target.id}:{target.kind.value}",
        f"budget_profile:{budget_decision.profile}",
        *budget_decision.evidence,
    ]
    if mappings:
        evidence.append(f"mapping_count:{len(mappings)}")
        evidence.extend(f"mapping:{mapping.id}:{mapping.relationship.value}:{mapping.confidence}" for mapping in mappings[:8])

    return ContextProjection(
        active_session_id=target.id,
        source_session_ids=[source.id],
        projection_mode=ProjectionMode.BEHAVIOR_MAP if broad_source and focused_target else ProjectionMode.SUMMARY,
        projection_source=ProjectionSource.MAPPING_BASED if mapping_based else ProjectionSource.HEURISTIC,
        relevance_score=0.6 if mapping_based else 0.5,
        evidence=list(dict.fromkeys(evidence)),
        include_selectors=list(dict.fromkeys(include_selectors)),
        exclude_selectors=list(dict.fromkeys(exclude_selectors)),
        budget=budget_decision.budget,
        rationale=f"{budget_decision.rationale} Project {source.title} into {target.title} without rewriting source identity.",
    )
