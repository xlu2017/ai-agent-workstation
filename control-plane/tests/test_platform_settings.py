import sys
from pathlib import Path

# Add control-plane root to path
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_observability_settings_roundtrip(tmp_path):
    from api.services.platform_settings import (
        ObservabilitySettings,
        PlatformSettings,
        load_platform_settings,
        save_platform_settings,
    )

    path = tmp_path / "settings.json"
    settings = PlatformSettings(
        observability=ObservabilitySettings(
            logging_extent="verbose",
            lookback_hours=72,
            include_ambient_context=True,
            include_debug_prompts=False,
            include_tool_outputs=True,
            max_events_per_session=5000,
        )
    )

    save_platform_settings(settings, path=path)
    loaded = load_platform_settings(path=path)

    assert loaded.observability.logging_extent == "verbose"
    assert loaded.observability.lookback_hours == 72
    assert loaded.observability.max_events_per_session == 5000


def test_observability_settings_reject_invalid_lookback():
    from pydantic import ValidationError
    from api.services.platform_settings import ObservabilitySettings

    try:
        ObservabilitySettings(lookback_hours=13)
    except ValidationError as exc:
        assert "lookback_hours" in str(exc)
    else:
        raise AssertionError("Expected invalid lookback to fail validation")
