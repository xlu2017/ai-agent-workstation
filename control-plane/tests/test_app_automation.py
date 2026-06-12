"""Tests for app automation vendor/action scaffold."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api.app_automation.registry import list_actions, list_vendor_tools  # noqa: E402


def _client():
    return TestClient(app)


def test_vendor_manifest_loads_selected_tools():
    vendors = list_vendor_tools()

    ids = {vendor.id for vendor in vendors}
    assert "activepieces" in ids
    assert "composio" in ids
    assert "mcp_servers" in ids
    assert "stagehand" in ids
    assert "browser_use" in ids
    assert "skyvern" in ids


def test_actions_cover_seed_apps():
    actions = list_actions()
    app_ids = {action.app_id for action in actions}

    for app_id in {"github", "slack", "gmail", "google_calendar", "google_sheets", "notion", "linear", "jira", "discord", "hubspot", "web"}:
        assert app_id in app_ids


def test_vendors_endpoint_reports_install_status():
    response = _client().get("/api/app-automation/vendors")

    assert response.status_code == 200
    data = response.json()
    assert "api" in data["default_execution_ladder"]
    assert any(vendor["id"] == "activepieces" for vendor in data["vendors"])
    assert all("installed" in vendor for vendor in data["vendors"])


def test_actions_endpoint_can_filter_by_app():
    response = _client().get("/api/app-automation/actions?app_id=github")

    assert response.status_code == 200
    actions = response.json()["actions"]
    assert actions
    assert all(action["app_id"] == "github" for action in actions)


def test_execute_read_only_action_dry_run_plans():
    response = _client().post("/api/app-automation/execute", json={
        "app_id": "github",
        "action_id": "github.search_repo",
        "params": {"repo": "xlu2017/jubilant-goggles", "query": "executor"},
        "dry_run": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "planned"
    assert data["required_approval"] is False
    assert data["vendor"] == "mcp_servers"


def test_execute_side_effect_action_requires_approval():
    response = _client().post("/api/app-automation/execute", json={
        "app_id": "slack",
        "action_id": "slack.send_message",
        "params": {"channel": "engineering", "text": "hello"},
        "dry_run": False,
        "approval_granted": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "needs_approval"
    assert data["required_approval"] is True


def test_execute_unknown_action_returns_structured_error():
    response = _client().post("/api/app-automation/execute", json={
        "app_id": "missing",
        "action_id": "missing.action",
        "params": {},
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "UNKNOWN_ACTION"
