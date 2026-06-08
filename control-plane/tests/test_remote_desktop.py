import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app


def _client():
    return TestClient(app)


def test_remote_desktop_config_hides_secrets(monkeypatch):
    monkeypatch.setenv("REMOTE_DESKTOP_ENABLED", "true")
    monkeypatch.setenv("GUACAMOLE_AUTO_LOGIN_ENABLED", "true")
    monkeypatch.setenv("GUACAMOLE_URL", "/guacamole/")
    monkeypatch.setenv("RDP_HOST", "dev-server")
    monkeypatch.setenv("RDP_USERNAME", "agent")
    monkeypatch.setenv("RDP_PASSWORD", "do-not-return")

    response = _client().get("/api/v2/remote-desktop/config")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "enabled": True,
        "provider": "guacamole",
        "url": "/guacamole/",
        "rdp_host": "dev-server",
        "security": "tailscale_only",
        "auto_login": True,
    }
    assert "RDP_PASSWORD" not in response.text
    assert "do-not-return" not in response.text
    assert "agent" not in response.text


def test_remote_desktop_token_hides_credentials(monkeypatch):
    monkeypatch.setenv("REMOTE_DESKTOP_ENABLED", "true")
    monkeypatch.setenv("GUACAMOLE_AUTO_LOGIN_ENABLED", "true")
    monkeypatch.setenv("GUACAMOLE_URL", "/guacamole/")
    monkeypatch.setenv("GUACAMOLE_USERNAME", "guacadmin")
    monkeypatch.setenv("GUACAMOLE_PASSWORD", "do-not-return")
    monkeypatch.setenv("GUACAMOLE_CONNECTION_ID", "1")

    token = {
        "authToken": "token-value",
        "username": "guacadmin",
        "dataSource": "postgresql",
        "availableDataSources": ["postgresql"],
    }
    with patch("api.server._request_guacamole_token", return_value=token):
        response = _client().post("/api/v2/remote-desktop/token")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "authToken": "token-value",
        "username": "guacadmin",
        "dataSource": "postgresql",
        "availableDataSources": ["postgresql"],
        "connection_url": "/guacamole/#/client/MQBjAHBvc3RncmVzcWw",
    }
    assert "GUACAMOLE_PASSWORD" not in response.text
    assert "do-not-return" not in response.text


def test_remote_desktop_token_rejects_when_auto_login_disabled(monkeypatch):
    monkeypatch.setenv("REMOTE_DESKTOP_ENABLED", "true")
    monkeypatch.setenv("GUACAMOLE_AUTO_LOGIN_ENABLED", "false")

    response = _client().post("/api/v2/remote-desktop/token")

    assert response.status_code == 409


def test_remote_desktop_config_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REMOTE_DESKTOP_ENABLED", raising=False)

    response = _client().get("/api/v2/remote-desktop/config")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_remote_desktop_health_handles_guacamole_down(monkeypatch):
    monkeypatch.setenv("REMOTE_DESKTOP_ENABLED", "true")
    monkeypatch.setenv("RDP_HOST", "dev-server")

    with patch("api.server._check_http", return_value={"status": "unreachable", "error": "down"}):
        with patch("api.server._check_tcp", return_value={"status": "reachable"}):
            response = _client().get("/api/v2/remote-desktop/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["guacamole"] == "unreachable"
    assert data["rdp"] == "reachable"
    assert data["rdp_host"] == "dev-server"


def test_remote_desktop_health_handles_rdp_unreachable(monkeypatch):
    monkeypatch.setenv("REMOTE_DESKTOP_ENABLED", "true")
    monkeypatch.setenv("RDP_HOST", "dev-server")
    monkeypatch.setenv("RDP_PORT", "3389")

    with patch("api.server._check_http", return_value={"status": "reachable", "code": 200}):
        with patch("api.server._check_tcp", return_value={"status": "unreachable", "error": "refused"}):
            response = _client().get("/api/v2/remote-desktop/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["guacamole"] == "reachable"
    assert data["rdp"] == "unreachable"
    assert data["rdp_port"] == 3389


def test_dashboard_route_renders_disabled_instructions():
    app_source = Path(__file__).parents[1] / "web" / "src" / "App.tsx"
    content = app_source.read_text()

    assert "routePath === '/remote-desktop'" in content
    assert "Remote desktop is disabled" in content
    assert "REMOTE_DESKTOP_ENABLED=true" in content
    assert "remote-desktop/token" in content
    assert "docker-compose.guacamole.yml" in content
