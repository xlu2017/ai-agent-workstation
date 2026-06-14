from __future__ import annotations

from typing import Any

from api.models.session_graph import (
    ContextProjection,
    MountSessionRequest,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
    SessionKind,
    SessionRecord,
)
from api.services.context_projection_budget import select_context_projection_budget


def _mapping_value(mapping: object, name: str, default: object = "") -> object:
    if isinstance(mapping, dict):
        return mapping.get(name, default)
    return getattr(mapping, name, default)


def _enumish_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def generate_budgeted_context_projection(
    source: SessionRecord,
    target: SessionRecord,
    request: MountSessionRequest,
    mappings: list[Any] | None = None,
) -> ContextProjection:
    """Generate a task-scoped projection with dynamic budget evidence.

    This service is graph-model-native. Deprecated adapter-engine mapping objects
    may still be passed as loose evidence, but they are not required.
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
        f"budget_rationale:{budget_decision.budget_rationale}",
        *budget_decision.evidence,
    ]
    if mappings:
        evidence.append(f"mapping_count:{len(mappings)}")
        for mapping in mappings[:8]:
            evidence.append(f"mapping:{_mapping_value(mapping, 'id', '')}:{_enumish_value(_mapping_value(mapping, 'relationship', ''))}:{_mapping_value(mapping, 'confidence', '')}")

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
        rationale=(
            f"Budget rationale: {budget_decision.budget_rationale} "
            f"Project {source.title} into {target.title} without rewriting source identity."
        ),
    )
