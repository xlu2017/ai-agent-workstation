import sys
from datetime import datetime, timedelta, timezone
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


def test_event_store_can_apply_observability_settings(monkeypatch, tmp_path):
    from api.services.platform_settings import ObservabilitySettings
    from live_feed.events import EventStore, EventType, create_event

    store = EventStore(tmp_path)
    old_event = create_event(EventType.ACTION_PROGRESS, "s1", message="old")
    old_event.timestamp = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    current_event = create_event(EventType.ACTION_COMPLETED, "s1", message="current")
    ambient_event = create_event(EventType.AMBIENT_CONTEXT_COLLECTED, "s1", message="ambient")

    store.append(old_event)
    store.append(current_event)
    store.append(ambient_event)

    class FakeSettings:
        lookback_hours = 24
        max_events_per_session = 100
        include_ambient_context = False
        include_debug_prompts = False
        include_tool_outputs = True
        logging_extent = "standard"

    monkeypatch.setattr("live_feed.events._safe_observability_settings", lambda: FakeSettings())

    events = store.get_events("s1")
    assert [event["event_type"] for event in events] == ["action_completed"]

    unfiltered = store.get_events("s1", apply_observability_settings=False)
    assert len(unfiltered) == 3
