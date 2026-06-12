from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_ENV_VALUES


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AmbientCollectorConfig:
    """Environment-backed configuration for ambient context collection.

    The platform should survive server topology changes. Do not encode a single
    browser port, desktop command, or session root as a hard dependency.
    """

    sessions_dir: Path = field(default_factory=lambda: Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions")))
    repos_dir: Path = field(default_factory=lambda: Path(os.environ.get("REPOS_DIR", "/opt/workstation/repos")))
    bridge_url: str = field(default_factory=lambda: os.environ.get("BRIDGE_URL", "http://127.0.0.1:9876"))
    browser_debug_urls: list[str] = field(default_factory=lambda: env_list(
        "AMBIENT_BROWSER_DEBUG_URLS",
        [
            "http://127.0.0.1:9222",
            "http://127.0.0.1:9223",
            "http://127.0.0.1:9224",
        ],
    ))
    browser_timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("AMBIENT_BROWSER_TIMEOUT_SECONDS", "1.5")))
    desktop_enabled: bool = field(default_factory=lambda: env_bool("AMBIENT_DESKTOP_ENABLED", True))
    browser_enabled: bool = field(default_factory=lambda: env_bool("AMBIENT_BROWSER_ENABLED", True))
    repo_enabled: bool = field(default_factory=lambda: env_bool("AMBIENT_REPO_ENABLED", True))
    legacy_context_enabled: bool = field(default_factory=lambda: env_bool("AMBIENT_LEGACY_CONTEXT_ENABLED", True))
    runtime_enabled: bool = field(default_factory=lambda: env_bool("AMBIENT_RUNTIME_ENABLED", True))
    max_events_per_collect: int = field(default_factory=lambda: env_int("AMBIENT_MAX_EVENTS_PER_COLLECT", 100))


def get_ambient_config() -> AmbientCollectorConfig:
    return AmbientCollectorConfig()
