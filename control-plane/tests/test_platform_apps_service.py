import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.platform_apps import DesktopEntry, ProcessMatch, discover_popular_applications


def test_platform_apps_search_prioritizes_matching_installed_apps(monkeypatch):
    monkeypatch.setattr("api.services.platform_apps._desktop_entries", lambda: [])
    monkeypatch.setattr("api.services.platform_apps._process_rows", lambda: [])
    monkeypatch.setattr("api.services.platform_apps._window_rows", lambda: [])
    monkeypatch.setattr("api.services.platform_apps.shutil.which", lambda command: "/usr/bin/xfce4-terminal" if command == "xfce4-terminal" else None)

    results = discover_popular_applications("terminal")

    assert results
    assert results[0]["id"] == "terminal"
    assert results[0]["installed"] is True
    assert results[0]["running"] is False
    assert results[0]["confidence"] == "installed"
    assert results[0]["launchCommand"] == "xfce4-terminal"
    assert "preferredCommands" in results[0]
    assert "fallbackCommands" in results[0]
    assert "matchedCommands" in results[0]


def test_platform_apps_detects_desktop_file_aliases_without_exact_command(monkeypatch):
    entries = [
        DesktopEntry(
            path="/usr/share/applications/org.gnome.Nautilus.desktop",
            name="Files",
            generic_name="File Manager",
            categories=["System", "FileManager"],
            keywords=["folder", "filesystem"],
            exec_command="nautilus",
        )
    ]
    monkeypatch.setattr("api.services.platform_apps._desktop_entries", lambda: entries)
    monkeypatch.setattr("api.services.platform_apps._process_rows", lambda: [])
    monkeypatch.setattr("api.services.platform_apps._window_rows", lambda: [])
    monkeypatch.setattr("api.services.platform_apps.shutil.which", lambda command: None)

    results = discover_popular_applications("files")
    file_manager = results[0]

    assert file_manager["id"] == "file-manager"
    assert file_manager["installed"] is True
    assert file_manager["confidence"] == "installed"
    assert file_manager["matchedDesktopFiles"] == ["/usr/share/applications/org.gnome.Nautilus.desktop"]
    assert file_manager["launchCommand"] == "nautilus"


def test_platform_apps_detects_running_processes(monkeypatch):
    monkeypatch.setattr("api.services.platform_apps._desktop_entries", lambda: [])
    monkeypatch.setattr("api.services.platform_apps._process_rows", lambda: [ProcessMatch(pid=4242, command="firefox", args="/usr/lib/firefox/firefox")])
    monkeypatch.setattr("api.services.platform_apps._window_rows", lambda: [])
    monkeypatch.setattr("api.services.platform_apps.shutil.which", lambda command: "/usr/bin/firefox" if command == "firefox" else None)

    results = discover_popular_applications("browser")
    browser = results[0]

    assert browser["id"] == "browser"
    assert browser["running"] is True
    assert browser["confidence"] == "running"
    assert browser["matchedProcesses"][0]["pid"] == 4242
