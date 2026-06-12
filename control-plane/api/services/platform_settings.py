from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SETTINGS_FILE = Path(
    os.environ.get(
        "PLATFORM_SETTINGS_FILE",
        "/opt/workstation/sessions/platform-settings.json",
    )
)

LoggingLevel = Literal["minimal", "standard", "verbose", "diagnostic"]


class ObservabilitySettings(BaseModel):
    """Controls how much session telemetry is collected and how far back UIs look."""

    logging_extent: LoggingLevel = "standard"
    lookback_hours: int = Field(default=24, ge=1, le=720)
    include_ambient_context: bool = True
    include_debug_prompts: bool = False
    include_tool_outputs: bool = True
    max_events_per_session: int = Field(default=1000, ge=100, le=50000)

    @field_validator("lookback_hours")
    @classmethod
    def validate_lookback(cls, value: int) -> int:
        if value not in {1, 6, 12, 24, 72, 168, 720}:
            raise ValueError("lookback_hours must be one of 1, 6, 12, 24, 72, 168, 720")
        return value


class PlatformSettings(BaseModel):
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


def load_platform_settings(path: Path = SETTINGS_FILE) -> PlatformSettings:
    if not path.exists():
        return PlatformSettings()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return PlatformSettings()
    return PlatformSettings.model_validate(data)


def save_platform_settings(settings: PlatformSettings, path: Path = SETTINGS_FILE) -> PlatformSettings:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return settings


def get_observability_settings() -> ObservabilitySettings:
    return load_platform_settings().observability


def update_observability_settings(update: ObservabilitySettings) -> ObservabilitySettings:
    settings = load_platform_settings()
    settings.observability = update
    save_platform_settings(settings)
    return settings.observability
