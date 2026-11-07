"""Tests for app automation vendor/action scaffold."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api.app_automation.registry import list_actions, list_vendor_tools, vendor_status  # noqa: E402
from api.app_automation.vendor_plan import build_action_plan, vendor_profile_matrix  # noqa: E402


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


def test_vendored_sources_are_present_for_all_selected_tools():
    statuses = vendor_status()

    installed = {vendor["id"]: vendor["installed"] for vendor in statuses}
    for vendor_id in {"activepieces", "composio", "mcp_servers", "n8n", "stagehand", "browser_use", "skyvern"}:
        assert installed[vendor_id] is True


def test_local_vendor_adapters_are_present_for_runtime_contracts():
    statuses = vendor_status()

    local_adapters = {vendor["id"]: vendor["local_adapter_present"] for vendor in statuses}
    for vendor_id in {"activepieces", "composio", "mcp_servers", "n8n", "stagehand", "browser_use", "skyvern"}:
        assert local_adapters[vendor_id] is True


def test_capability_matrix_orders_vendors_by_execution_ladder():
    matrix = vendor_profile_matrix()

    assert [row["vendor"] for row in matrix][:3] == ["composio", "mcp_servers", "activepieces"]
    assert any(row["vendor"] == "skyvern" and row["layer"] == "visual_browser" for row in matrix)
    assert all("handoff_to" in row for row in matrix)


def test_actions_cover_seed_apps():
    actions = list_actions()
    app_ids = {action.app_id for action in actions}

    for app_id in {"github", "slack", "gmail", "google_calendar", "google_sheets", "notion", "linear", "jira", "discord", "hubspot", "web"}:
        assert app_id in app_ids


def test_action_plan_contains_vendor_fallback_chain():
    action = next(action for action in list_actions() if action.id == "web.perform_task")
    plan = build_action_plan(action)

    assert plan["selected_vendor"] in {"stagehand", "browser_use", "skyvern"}
    assert [candidate["vendor"] for candidate in plan["candidates"]] == ["stagehand", "browser_use", "skyvern"]
    assert "browser" in plan["execution_ladder"]


def test_vendors_endpoint_reports_install_status_capabilities_and_local_adapters():
    response = _client().get("/api/app-automation/vendors")

    assert response.status_code == 200
    data = response.json()
    assert "api" in data["default_execution_ladder"]
    assert any(vendor["id"] == "activepieces" for vendor in data["vendors"])
    assert all("installed" in vendor for vendor in data["vendors"])
    assert all("local_adapter_present" in vendor for vendor in data["vendors"])
    assert any(row["vendor"] == "composio" for row in data["capability_matrix"])


def test_capabilities_endpoint_reports_layers():
    response = _client().get("/api/app-automation/capabilities")

    assert response.status_code == 200
    matrix = response.json()["capability_matrix"]
    assert any(row["layer"] == "api" for row in matrix)
    assert any(row["layer"] == "workflow" for row in matrix)
    assert any(row["layer"] == "visual_browser" for row in matrix)


def test_action_plan_endpoint_reports_candidates():
    response = _client().get("/api/app-automation/actions/github.search_repo/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["plan"]["selected_vendor"] == "mcp_servers"
    assert data["plan"]["candidates"]


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
        "params": {"repo": "xlu2017/ai-agent-workstation", "query": "executor"},
        "dry_run": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "planned"
    assert data["required_approval"] is False
    assert data["vendor"] == "mcp_servers"
    assert data["route_plan"]["selected_vendor"] == "mcp_servers"


def test_execute_read_only_action_completes_with_mock_runtime(monkeypatch):
    monkeypatch.setenv("APP_AUTOMATION_MOCK", "true")

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "github",
        "action_id": "github.search_repo",
        "params": {"repo": "xlu2017/ai-agent-workstation", "query": "executor"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "completed"
    assert data["vendor"] == "mcp_servers"
    assert data["result"]["mock"] is True
    assert data["result"]["action_id"] == "github.search_repo"
    assert data["route_plan"]["candidates"][0]["vendor"] == "mcp_servers"


def test_execute_unconfigured_http_vendor_uses_vendored_local_adapter_contract(monkeypatch):
    monkeypatch.delenv("APP_AUTOMATION_MOCK", raising=False)
    monkeypatch.delenv("COMPOSIO_PROXY_URL", raising=False)
    monkeypatch.delenv("APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS", raising=False)

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "gmail",
        "action_id": "gmail.search_email",
        "params": {"query": "from:test@example.com"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "adapter_contract_completed"
    assert data["result"]["vendor"] == "composio"
    assert data["result"]["external_side_effect_performed"] is False


def test_disabling_local_vendor_adapter_restores_runtime_not_configured(monkeypatch):
    monkeypatch.delenv("APP_AUTOMATION_MOCK", raising=False)
    monkeypatch.delenv("COMPOSIO_PROXY_URL", raising=False)
    monkeypatch.setenv("APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS", "false")

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "gmail",
        "action_id": "gmail.search_email",
        "params": {"query": "from:test@example.com"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "runtime_not_configured"
    assert data["error"]["code"] == "RUNTIME_NOT_CONFIGURED"


def test_browser_action_uses_stagehand_local_adapter_contract(monkeypatch):
    monkeypatch.delenv("APP_AUTOMATION_MOCK", raising=False)
    monkeypatch.delenv("STAGEHAND_COMMAND", raising=False)
    monkeypatch.delenv("APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS", raising=False)

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "web",
        "action_id": "web.perform_task",
        "params": {"url": "https://example.com", "instruction": "summarize page"},
        "dry_run": False,
        "approval_granted": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "adapter_contract_completed"
    assert data["vendor"] == "stagehand"
    assert data["result"]["browser_launched"] is False


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
    assert data["route_plan"]["selected_vendor"] == "composio"


def test_execute_side_effect_action_completes_with_mock_after_approval(monkeypatch):
    monkeypatch.setenv("APP_AUTOMATION_MOCK", "true")

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "slack",
        "action_id": "slack.send_message",
        "params": {"channel": "engineering", "text": "hello"},
        "dry_run": False,
        "approval_granted": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "completed"
    assert data["vendor"] == "composio"
    assert data["result"]["mock"] is True


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


def test_execute_invalid_params_rejects_before_runtime_and_records_event(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_AUTOMATION_MOCK", "true")
    monkeypatch.setenv("APP_AUTOMATION_EVENTS_DIR", str(tmp_path))
    session_id = "app-auto-invalid-params"

    response = _client().post("/api/app-automation/execute", json={
        "session_id": session_id,
        "app_id": "github",
        "action_id": "github.search_repo",
        "params": {"repo": "xlu2017/ai-agent-workstation"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "invalid_params"
    assert data["error"]["code"] == "ACTION_PARAMS_INVALID"

    events = _client().get(f"/api/app-automation/events/{session_id}").json()["events"]
    assert [event["event_type"] for event in events] == ["app_automation_planned", "app_automation_validation_failed"]
    assert events[-1]["data"]["error"]["issues"][0]["path"] == ["query"]


def test_execute_mock_runtime_records_executed_event_and_redacts_sensitive_params(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_AUTOMATION_MOCK", "true")
    monkeypatch.setenv("APP_AUTOMATION_EVENTS_DIR", str(tmp_path))
    session_id = "app-auto-executed"

    response = _client().post("/api/app-automation/execute", json={
        "session_id": session_id,
        "app_id": "github",
        "action_id": "github.search_repo",
        "params": {"repo": "xlu2017/ai-agent-workstation", "query": "executor", "api_key": "should-not-persist"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "completed"

    events_response = _client().get(f"/api/app-automation/events/{session_id}")
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert [event["event_type"] for event in events] == ["app_automation_planned", "app_automation_executed"]
    assert events[0]["data"]["params_preview"]["api_key"] == "[REDACTED]"
    assert events[-1]["data"]["status"] == "completed"
    assert events[-1]["data"]["result"]["mock"] is True


def test_approval_block_records_blocked_event(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_AUTOMATION_EVENTS_DIR", str(tmp_path))
    session_id = "app-auto-approval-block"

    response = _client().post("/api/app-automation/execute", json={
        "session_id": session_id,
        "app_id": "slack",
        "action_id": "slack.send_message",
        "params": {"channel": "engineering", "text": "hello"},
        "dry_run": False,
        "approval_granted": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "needs_approval"

    events = _client().get(f"/api/app-automation/events/{session_id}").json()["events"]
    assert [event["event_type"] for event in events] == ["app_automation_planned", "app_automation_blocked"]
    assert events[-1]["data"]["required_approval"] is True
