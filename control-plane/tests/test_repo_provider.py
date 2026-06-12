"""Tests for repo provider selection and GitHub login scaffold."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api import repo_provider  # noqa: E402
from api import service_updater  # noqa: E402


def _client():
    return TestClient(app)


def _isolate_provider_files(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_provider, "CONFIG_PATH", tmp_path / "repo-provider.json")
    monkeypatch.setattr(repo_provider, "SECRETS_PATH", tmp_path / "repo-provider-secrets.json")


def test_repo_provider_status_defaults_to_env_pat(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")

    response = _client().get("/api/repo-provider/status")

    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "personal_access_token"
    assert data["effective_token_available"] is True
    pat = next(provider for provider in data["providers"] if provider["id"] == "personal_access_token")
    assert pat["connected"] is True


def test_repo_provider_can_select_none(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")

    response = _client().post("/api/repo-provider/select", json={"provider": "none"})

    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "none"
    assert data["effective_token_available"] is False


def test_service_updater_uses_selected_repo_provider(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    _client().post("/api/repo-provider/select", json={"provider": "none"})

    assert service_updater._get_token() is None

    _client().post("/api/repo-provider/select", json={"provider": "personal_access_token"})
    assert service_updater._get_token() == "unit-test-token"


def test_github_login_url_reports_missing_oauth_config(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_SECRET", raising=False)

    response = _client().get("/api/repo-provider/github/login-url")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "GITHUB_OAUTH_NOT_CONFIGURED"


def test_github_login_url_returns_authorization_url(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "client-secret")

    response = _client().get("/api/repo-provider/github/login-url?redirect_uri=http://testserver/api/repo-provider/github/callback")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "github.com/login/oauth/authorize" in data["login_url"]
    assert "client_id=client-id" in data["login_url"]


def test_github_disconnect_falls_back_to_pat(tmp_path, monkeypatch):
    _isolate_provider_files(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    repo_provider.select_repo_provider("github_oauth")
    repo_provider.save_repo_provider_secrets({"github_oauth": {"access_token": "oauth-token"}})

    response = _client().post("/api/repo-provider/github/disconnect")

    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "personal_access_token"
    assert data["effective_token_available"] is True
