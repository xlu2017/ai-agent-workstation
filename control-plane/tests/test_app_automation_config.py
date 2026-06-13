"""Tests for app automation runtime configuration endpoints."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api.app_automation import config as app_config  # noqa: E402


def _client():
    return TestClient(app)


def test_config_endpoint_reports_unconfigured_vendors(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "app-automation-runtime.json")
    monkeypatch.delenv("COMPOSIO_PROXY_URL", raising=False)

    response = _client().get("/api/app-automation/config")

    assert response.status_code == 200
    data = response.json()
    composio = next(item for item in data["vendors"] if item["vendor_id"] == "composio")
    assert composio["configurable"] is True
    assert composio["configured"] is False
    assert composio["config_source"] == "unconfigured"
    assert composio["kind"] == "url"
    assert composio["can_edit"] is True


def test_can_save_and_clear_vendor_runtime_config(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "app-automation-runtime.json")
    monkeypatch.delenv("COMPOSIO_PROXY_URL", raising=False)

    saved = _client().put("/api/app-automation/config/composio", json={
        "value": "https://internal.example/app-automation/composio?token=secret",
        "enabled": True,
    })

    assert saved.status_code == 200
    saved_data = saved.json()
    assert saved_data["configured"] is True
    assert saved_data["config_source"] == "stored"
    assert saved_data["value_preview"] != "https://internal.example/app-automation/composio?token=secret"
    assert app_config.get_runtime_value("composio") == "https://internal.example/app-automation/composio?token=secret"

    cleared = _client().delete("/api/app-automation/config/composio")

    assert cleared.status_code == 200
    assert cleared.json()["config_source"] == "unconfigured"
    assert app_config.get_runtime_value("composio") is None


def test_environment_config_overrides_stored_config(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "app-automation-runtime.json")
    monkeypatch.setenv("COMPOSIO_PROXY_URL", "https://env.example/composio")

    response = _client().put("/api/app-automation/config/composio", json={"value": "https://stored.example/composio", "enabled": True})
    assert response.status_code == 200

    status = _client().get("/api/app-automation/config/composio").json()
    assert status["configured"] is True
    assert status["config_source"] == "environment"
    assert status["can_edit"] is False
    assert app_config.get_runtime_value("composio") == "https://env.example/composio"


def test_config_rejects_empty_enabled_value(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "app-automation-runtime.json")

    response = _client().put("/api/app-automation/config/stagehand", json={"value": "", "enabled": True})

    assert response.status_code == 400
    assert "Configuration value is required" in response.text


def test_vendors_endpoint_embeds_runtime_config(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "CONFIG_PATH", tmp_path / "app-automation-runtime.json")
    monkeypatch.delenv("ACTIVEPIECES_WEBHOOK_URL", raising=False)

    response = _client().get("/api/app-automation/vendors")

    assert response.status_code == 200
    vendors = response.json()["vendors"]
    activepieces = next(item for item in vendors if item["id"] == "activepieces")
    assert activepieces["runtime_config"]["vendor_id"] == "activepieces"
    assert activepieces["runtime_config"]["configurable"] is True
