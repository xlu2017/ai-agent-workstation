"""Alias normalization scaffold for recommend-next action envelopes.

This module is scaffold-only. It normalizes app-specific catalog action names to
provider-neutral top-level action names without changing runtime behavior.
"""

from __future__ import annotations

from typing import Any, Mapping

from execution.recommend_next_action_envelope_schema import (
    ActionAliasNormalization,
    ParameterSchemaValidationResult,
    RecommendNextActionEnvelope,
)
from execution.recommend_next_app_automation_provider_inventory import (
    APP_CATALOG_ACTION_ALIASES,
    TOP_LEVEL_ACTION_PARAMETER_SCHEMAS,
)
from execution.recommend_next_execution_service import RecommendNextDecisionType


def normalize_catalog_action_alias(action_name: str, params: Mapping[str, Any] | None = None) -> ActionAliasNormalization:
    """Normalize app-specific catalog action names to top-level action names.

    Provider or app specificity is preserved in params. The raw catalog action
    ID is preserved as metadata for the future app-automation executor bridge.
    """

    raw_params = dict(params or {})
    top_level_action_name = APP_CATALOG_ACTION_ALIASES.get(action_name, action_name)
    catalog_action_id = action_name if top_level_action_name != action_name else raw_params.get("catalog_action_id")
    schema = TOP_LEVEL_ACTION_PARAMETER_SCHEMAS.get(top_level_action_name)

    if schema and schema.provider_parameter and schema.provider_parameter not in raw_params:
        inferred_provider = _infer_provider_from_catalog_action_id(action_name)
        if inferred_provider:
            raw_params[schema.provider_parameter] = inferred_provider

    if catalog_action_id and "catalog_action_id" not in raw_params:
        raw_params["catalog_action_id"] = catalog_action_id

    return ActionAliasNormalization(
        source_action_name=action_name,
        top_level_action_name=top_level_action_name,
        normalized_params=raw_params,
        catalog_action_id=str(catalog_action_id) if catalog_action_id else None,
    )


def validate_top_level_action_params(action_name: str, params: Mapping[str, Any] | None = None) -> ParameterSchemaValidationResult:
    """Validate only the scaffolded top-level parameter shape.

    Future runtime validation must still enforce credentials, approval, policy,
    permissions, and provider-specific contracts.
    """

    raw_params = dict(params or {})
    schema = TOP_LEVEL_ACTION_PARAMETER_SCHEMAS.get(action_name)
    if not schema:
        return ParameterSchemaValidationResult(
            ok=False,
            action_name=action_name,
            notes=("No scaffold parameter schema exists for this top-level action.",),
        )

    missing = tuple(name for name in schema.required_parameters if not raw_params.get(name))
    unknown_provider_parameter = None
    if schema.provider_parameter:
        for key in raw_params:
            if key.endswith("_provider") and key != schema.provider_parameter:
                unknown_provider_parameter = key
                break

    return ParameterSchemaValidationResult(
        ok=not missing and unknown_provider_parameter is None,
        action_name=action_name,
        missing_required_parameters=missing,
        unknown_provider_parameter=unknown_provider_parameter,
    )


def make_provider_neutral_envelope(
    action_name: str,
    decision_type: RecommendNextDecisionType,
    params: Mapping[str, Any] | None = None,
    rationale: str = "",
) -> RecommendNextActionEnvelope:
    """Build a provider-neutral envelope from a raw action name.

    App-specific aliases are normalized before the envelope is created. This is
    not wired into runtime behavior yet.
    """

    normalized = normalize_catalog_action_alias(action_name, params)
    raw_params = dict(normalized.normalized_params)
    automation_vendor = raw_params.get("automation_vendor")
    catalog_action_id = normalized.catalog_action_id or raw_params.get("catalog_action_id")
    return RecommendNextActionEnvelope(
        action_name=normalized.top_level_action_name,
        decision_type=decision_type,
        params=raw_params,
        source_action_name=normalized.source_action_name,
        catalog_action_id=str(catalog_action_id) if catalog_action_id else None,
        automation_vendor=str(automation_vendor) if automation_vendor else None,
        rationale=rationale,
    )


def _infer_provider_from_catalog_action_id(action_name: str) -> str | None:
    """Infer provider parameter value from legacy app-specific action IDs."""

    if "." not in action_name:
        return None
    return action_name.split(".", 1)[0]
