"""Regression coverage for active replacements of deprecated glue bridge routes."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from api import ambient as ambient_api  # noqa: E402
from api.server import app  # noqa: E402


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(ambient_api, "SESSIONS_DIR", tmp_path)
    return TestClient(app)


def test_ambient_events_route_is_not_swallowed_by_deprecated_sessions(tmp_path, monkeypatch):
    response = _client(tmp_path, monkeypatch).post("/api/sessions/s1/ambient/events", json={
        "event_type": "browser.element_selected",
        "session_id": "s1",
        "source": "browser",
        "actor": "user",
        "confidence": 0.9,
        "payload": {"selector": "button[type=submit]", "component": "LoginForm"},
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event"]["event_type"] == "browser.element_selected"


def test_terminal_completed_route_replaces_legacy_terminal_watcher(tmp_path, monkeypatch):
    response = _client(tmp_path, monkeypatch).post("/api/sessions/s1/ambient/terminal/completed", json={
        "terminal_id": "term-1",
        "cwd": "/repo",
        "command": "pytest -q",
        "exit_code": 1,
        "stderr": "FAILED tests/test_login.py::test_login",
        "duration_ms": 1200,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    event = data["event"]
    assert event["event_type"] == "terminal.command_completed"
    assert event["payload"]["mentioned_files"] == ["tests/test_login.py"]
    assert event["payload"]["failure_summary"] == "FAILED tests/test_login.py::test_login"


def test_editor_selection_route_replaces_legacy_editor_context(tmp_path, monkeypatch):
    response = _client(tmp_path, monkeypatch).post("/api/sessions/s1/ambient/editor/selection", json={
        "path": "src/LoginForm.tsx",
        "start_line": 10,
        "end_line": 14,
        "selected_text": "submitLogin()",
        "symbol": "submitLogin",
    })

    assert response.status_code == 200
    event = response.json()["event"]
    assert event["event_type"] == "editor.selection_changed"
    assert event["payload"]["path"] == "src/LoginForm.tsx"
    assert event["payload"]["selected_text"] == "submitLogin()"
