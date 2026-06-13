"""Canonical recommend-next action envelope schema scaffold.

This module defines the future normalized shape that should cross the
recommend-next controller boundary. It is scaffold-only: no request handler,
workflow runner, or app-automation executor imports it yet.

Naming model:

* ``action_name`` is provider-neutral and root-taxonomy tracked.
* provider/app specificity lives in ``params``.
* app-specific catalog IDs are optional alias metadata.
* execution-vendor routing hints are optional metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from execution.recommend_next_execution_service import RecommendNextDecisionType


@dataclass(frozen=True)
class RecommendNextActionEnvelope:
    """Provider-neutral action envelope produced after recommend-next parsing.

    ``action_name`` must be a top-level provider-neutral name such as
    ``email.create`` or ``issue.create``. ``params`` may contain provider fields
    such as ``email_provider`` or ``issue_provider``.
    """

    action_name: str
    decision_type: RecommendNextDecisionType
    params: Mapping[str, Any] = field(default_factory=dict)
    source_action_name: str | None = None
    catalog_action_id: str | None = None
    automation_vendor: str | None = None
    rationale: str = ""


@dataclass(frozen=True)
class ActionAliasNormalization:
    """Scaffold record for alias-to-top-level normalization."""

    source_action_name: str
    top_level_action_name: str
    normalized_params: Mapping[str, Any] = field(default_factory=dict)
    catalog_action_id: str | None = None


@dataclass(frozen=True)
class ParameterSchemaValidationResult:
    """Scaffold validation result for top-level action parameter contracts."""

    ok: bool
    action_name: str
    missing_required_parameters: tuple[str, ...] = ()
    unknown_provider_parameter: str | None = None
    notes: tuple[str, ...] = ()
