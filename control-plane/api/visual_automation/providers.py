"""Provider registry and routing policy for screenshot-guided automation."""

from __future__ import annotations

import os
from typing import Iterable

from api.visual_automation.models import SurfaceKind, VisualProviderId, VisualProviderInfo, VisualTaskKind


_PROVIDER_ENV: dict[VisualProviderId, list[str]] = {
    "anthropic_computer_use": ["ANTHROPIC_API_KEY"],
    "gemini_computer_use": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openai_computer_use": ["OPENAI_API_KEY"],
    "plain_vision_verifier": ["VISUAL_VERIFIER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"],
}


def _configured(env_names: Iterable[str]) -> tuple[bool, list[str]]:
    configured = [name for name in env_names if os.environ.get(name)]
    return bool(configured), configured


def list_visual_providers() -> list[VisualProviderInfo]:
    anthropic_ok, anthropic_env = _configured(_PROVIDER_ENV["anthropic_computer_use"])
    gemini_ok, gemini_env = _configured(_PROVIDER_ENV["gemini_computer_use"])
    openai_ok, openai_env = _configured(_PROVIDER_ENV["openai_computer_use"])
    verifier_ok, verifier_env = _configured(_PROVIDER_ENV["plain_vision_verifier"])

    return [
        VisualProviderInfo(
            id="anthropic_computer_use",
            label="Anthropic Claude Computer Use",
            default_model=os.environ.get("ANTHROPIC_COMPUTER_USE_MODEL", "claude-sonnet-4-5"),
            configured=anthropic_ok,
            configured_env=anthropic_env,
            best_for=["desktop", "remote_desktop", "emulator", "browser"],
            supports_text_context=True,
            supports_terminal_output=True,
            supports_coordinates=True,
            supports_computer_actions=True,
            notes="Default for arbitrary GUI, Guacamole/VNC sessions, native apps, and emulators. Control plane executes requested actions.",
        ),
        VisualProviderInfo(
            id="gemini_computer_use",
            label="Gemini Computer Use",
            default_model=os.environ.get("GEMINI_COMPUTER_USE_MODEL", "gemini-2.5-computer-use-preview-10-2025"),
            configured=gemini_ok,
            configured_env=gemini_env,
            best_for=["browser"],
            supports_text_context=True,
            supports_terminal_output=True,
            supports_coordinates=True,
            supports_computer_actions=True,
            notes="Preferred browser/web-app provider when the target surface is known to be a browser session.",
        ),
        VisualProviderInfo(
            id="openai_computer_use",
            label="OpenAI Computer Use",
            default_model=os.environ.get("OPENAI_COMPUTER_USE_MODEL", "computer-use-preview"),
            configured=openai_ok,
            configured_env=openai_env,
            best_for=["desktop", "browser", "remote_desktop", "emulator", "high_resolution_fallback"],
            supports_text_context=True,
            supports_terminal_output=True,
            supports_coordinates=True,
            supports_computer_actions=True,
            notes="Fallback and evaluator provider for high-resolution screenshot interpretation and action proposals.",
        ),
        VisualProviderInfo(
            id="plain_vision_verifier",
            label="Plain vision verifier",
            default_model=os.environ.get("PLAIN_VISION_VERIFIER_MODEL", "provider-default-vision-model"),
            configured=verifier_ok,
            configured_env=verifier_env,
            best_for=["verification", "low_cost_state_check"],
            supports_text_context=True,
            supports_terminal_output=True,
            supports_coordinates=False,
            supports_computer_actions=False,
            notes="Verification-only path. Use before escalating to computer-use providers when no next click/type action is needed.",
        ),
    ]


def get_visual_provider(provider_id: VisualProviderId) -> VisualProviderInfo | None:
    for provider in list_visual_providers():
        if provider.id == provider_id:
            return provider
    return None


def choose_visual_provider(
    provider: VisualProviderId | str,
    task_kind: VisualTaskKind,
    surface_kind: SurfaceKind,
) -> VisualProviderInfo:
    if provider != "auto":
        selected = get_visual_provider(provider)  # type: ignore[arg-type]
        if not selected:
            raise ValueError(f"Unknown visual provider: {provider}")
        return selected

    providers = {item.id: item for item in list_visual_providers()}

    if task_kind == "verify_screen_state":
        verifier = providers["plain_vision_verifier"]
        if verifier.configured:
            return verifier
        if surface_kind == "browser" and providers["gemini_computer_use"].configured:
            return providers["gemini_computer_use"]
        if providers["anthropic_computer_use"].configured:
            return providers["anthropic_computer_use"]
        if providers["openai_computer_use"].configured:
            return providers["openai_computer_use"]
        return verifier

    if surface_kind == "browser" and providers["gemini_computer_use"].configured:
        return providers["gemini_computer_use"]
    if providers["anthropic_computer_use"].configured:
        return providers["anthropic_computer_use"]
    if providers["openai_computer_use"].configured:
        return providers["openai_computer_use"]
    if providers["gemini_computer_use"].configured:
        return providers["gemini_computer_use"]
    return providers["anthropic_computer_use"]
