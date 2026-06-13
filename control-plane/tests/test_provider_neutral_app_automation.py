"""Tests for provider-neutral app automation routing and execution."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from api.server import app  # noqa: E402
from api.app_automation.provider_neutral import resolve_provider_neutral_app_action  # noqa: E402
from api.app_automation.registry import list_actions  # noqa: E402


def _client():
    return TestClient(app)


def test_provider_neutral_actions_are_catalog_entries():
    action_ids = {action.id for action in list_actions()}

    for action_id in {
        "email.create",
        "email.search",
        "email.send",
        "message.send",
        "issue.create",
        "repository.search",
        "browser_task.perform",
        "visual_browser_task.perform",
    }:
        assert action_id in action_ids


def test_provider_specific_alias_normalizes_without_becoming_execution_action():
    resolved = resolve_provider_neutral_app_action(
        "outlook.create_email",
        {"to": "user@example.com"},
    )

    assert resolved.action_id == "email.create"
    assert resolved.app_id == "email"
    assert resolved.params["email_provider"] == "outlook"
    assert resolved.params["catalog_action_id"] == "outlook.create_email"


def test_provider_neutral_read_only_action_executes_through_vendor_adapter(monkeypatch):
    monkeypatch.delenv("APP_AUTOMATION_MOCK", raising=False)
    monkeypatch.delenv("COMPOSIO_PROXY_URL", raising=False)
    monkeypatch.delenv("APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS", raising=False)

    response = _client().post("/api/app-automation/execute", json={
        "app_id": "email",
        "action_id": "email.search",
        "params": {"email_provider": "gmail", "query": "from:test@example.com"},
        "dry_run": False,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "adapter_contract_completed"
    assert data["vendor"] == "composio"
    assert data["result"]["action_id"] == "email.search"
    assert data["result"]["external_side_effect_performed"] is False


@pytest.mark.asyncio
async def test_execution_router_dispatches_provider_neutral_app_action(monkeypatch):
    monkeypatch.setenv("APP_AUTOMATION_MOCK", "true")

    from adapters.execution.router import ExecutionRouter

    router = ExecutionRouter(agentic_enabled=False, allow_deterministic=False)
    result = await router.execute_action(
        "session-provider-neutral",
        "",
        "email.search",
        {"email_provider": "gmail", "query": "subject:test"},
        {},
    )

    assert result.status == "succeeded"
    assert result.backend == "app_automation"
    assert result.output["action_id"] == "email.search"
    assert result.output["result"]["mock"] is True
