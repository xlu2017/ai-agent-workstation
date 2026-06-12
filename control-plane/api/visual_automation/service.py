"""Service layer for visual verification and GUI action proposal.

This layer routes screenshot-context requests to a configured visual provider,
builds auditable request previews, normalizes provider action responses, and
returns policy-safe scaffold responses. It does not operate the GUI directly.
"""

from __future__ import annotations

from typing import Any

from api.visual_automation.models import (
    NormalizeProviderActionRequest,
    NormalizeProviderActionResult,
    ProposeGuiActionRequest,
    ProposeGuiActionResult,
    VerifyScreenRequest,
    VerifyScreenResult,
    VisualAction,
)
from api.visual_automation.normalizer import normalize_provider_actions
from api.visual_automation.providers import choose_visual_provider


def _observation_summary(observation) -> list[str]:
    evidence: list[str] = []
    if observation.screenshot:
        size = f"{observation.screenshot.width}x{observation.screenshot.height}" if observation.screenshot.width and observation.screenshot.height else "unknown size"
        evidence.append(f"Screenshot present ({observation.screenshot.media_type}, {size}, source={observation.screenshot.source or 'unknown'}).")
    if observation.terminal_output:
        evidence.append("Terminal output provided.")
    if observation.command_history:
        evidence.append(f"Command history entries: {len(observation.command_history)}.")
    if observation.dom_snapshot:
        evidence.append("DOM snapshot provided.")
    if observation.accessibility_tree:
        evidence.append("Accessibility tree provided.")
    if observation.ui_text:
        evidence.append("UI text provided.")
    return evidence


def _provider_request(provider_id: str, task: str, observation, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    content_kinds = []
    if observation.screenshot:
        content_kinds.append("screenshot")
    if observation.terminal_output:
        content_kinds.append("terminal_output")
    if observation.command_history:
        content_kinds.append("command_history")
    if observation.dom_snapshot:
        content_kinds.append("dom_snapshot")
    if observation.accessibility_tree:
        content_kinds.append("accessibility_tree")
    if observation.ui_text:
        content_kinds.append("ui_text")
    return {
        "provider": provider_id,
        "task": task,
        "goal": observation.goal,
        "surface_kind": observation.surface_kind,
        "content_kinds": content_kinds,
        "verification_criteria": observation.verification_criteria,
        "extra": extra or {},
    }


def verify_screen_state(request: VerifyScreenRequest) -> VerifyScreenResult:
    provider = choose_visual_provider(request.provider, "verify_screen_state", request.observation.surface_kind)
    raw_request = _provider_request(provider.id, "verify_screen_state", request.observation)
    evidence = _observation_summary(request.observation)

    if not provider.configured:
        return VerifyScreenResult(
            ok=False,
            provider=provider.id,
            status="uncertain",
            evidence=evidence,
            missing_information=["Configured provider credential."],
            message=f"Provider {provider.id} is not configured. Configure provider credentials before verification.",
            raw_provider_request=raw_request,
            error={"code": "PROVIDER_NOT_CONFIGURED", "message": f"Provider {provider.id} is not configured."},
        )

    if request.dry_run:
        return VerifyScreenResult(
            ok=True,
            provider=provider.id,
            status="uncertain",
            evidence=evidence,
            missing_information=["Provider call is disabled because dry_run=true."],
            message=f"Dry run: would ask {provider.label} to verify whether the screen satisfies the goal.",
            raw_provider_request=raw_request,
        )

    return VerifyScreenResult(
        ok=False,
        provider=provider.id,
        status="uncertain",
        evidence=evidence,
        missing_information=["Concrete provider adapter call is not wired yet."],
        message=f"Provider {provider.id} is configured, but verification adapter execution is not implemented yet.",
        raw_provider_request=raw_request,
        error={"code": "ADAPTER_NOT_WIRED", "message": "Visual verification adapter execution is not implemented yet."},
    )


def propose_gui_action(request: ProposeGuiActionRequest) -> ProposeGuiActionResult:
    provider = choose_visual_provider(request.provider, "propose_gui_action", request.observation.surface_kind)
    raw_request = _provider_request(provider.id, "propose_gui_action", request.observation, {"allowed_actions": request.allowed_actions})
    fallback_action = VisualAction(kind="screenshot") if "screenshot" in request.allowed_actions else VisualAction(kind="none")

    if not provider.configured:
        return ProposeGuiActionResult(
            ok=False,
            provider=provider.id,
            action=fallback_action,
            rationale="Provider is not configured; no GUI action can be proposed safely.",
            requires_approval=request.require_approval,
            message=f"Provider {provider.id} is not configured. Configure provider credentials before action proposal.",
            raw_provider_request=raw_request,
            error={"code": "PROVIDER_NOT_CONFIGURED", "message": f"Provider {provider.id} is not configured."},
        )

    if request.dry_run:
        return ProposeGuiActionResult(
            ok=True,
            provider=provider.id,
            action=fallback_action,
            rationale="Dry-run scaffold selected provider and built the request preview; no provider call or GUI operation was run.",
            confidence=None,
            requires_approval=request.require_approval,
            message=f"Dry run: would ask {provider.label} for the next GUI action.",
            raw_provider_request=raw_request,
        )

    return ProposeGuiActionResult(
        ok=False,
        provider=provider.id,
        action=fallback_action,
        rationale="Concrete provider adapter call is not wired yet.",
        confidence=None,
        requires_approval=request.require_approval,
        message=f"Provider {provider.id} is configured, but GUI action proposal adapter execution is not implemented yet.",
        raw_provider_request=raw_request,
        error={"code": "ADAPTER_NOT_WIRED", "message": "GUI action proposal adapter execution is not implemented yet."},
    )


def normalize_action_request(request: NormalizeProviderActionRequest) -> NormalizeProviderActionResult:
    actions = normalize_provider_actions(request.provider, request.raw_provider_response)
    return NormalizeProviderActionResult(
        ok=True,
        provider=request.provider,
        actions=actions,
        message=f"Normalized {len(actions)} action(s) from {request.provider} response.",
    )
