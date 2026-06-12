import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.platform_apps import discover_popular_applications


def test_platform_apps_search_prioritizes_matching_installed_apps(monkeypatch):
    monkeypatch.setattr("api.services.platform_apps._desktop_commands", lambda: set())
    monkeypatch.setattr("api.services.platform_apps.shutil.which", lambda command: "/usr/bin/xfce4-terminal" if command == "xfce4-terminal" else None)

    results = discover_popular_applications("terminal")

    assert results
    assert results[0]["id"] == "terminal"
    assert results[0]["installed"] is True
    assert "preferredCommands" in results[0]
    assert "launchPrompt" in results[0]
