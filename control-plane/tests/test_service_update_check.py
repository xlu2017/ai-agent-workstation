"""Tests for read-only repo-backed service update checks."""

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api import service_update_check  # noqa: E402


def _client():
    return TestClient(app)


def test_update_check_rejects_unknown_service():
    response = _client().get("/api/v2/services/nonexistent/update-check")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["ok"] is False
    assert detail["error"]["code"] == "UNKNOWN_SERVICE"


def test_update_check_reports_missing_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("PAT", raising=False)

    response = _client().get("/api/v2/services/agent-core/update-check")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "token_missing"
    assert data["error"]["code"] == "NO_TOKEN"


def test_update_check_reports_missing_checkout(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    monkeypatch.setattr(service_update_check, "_resolve_branch", lambda *_args, **_kwargs: ("main", None))
    monkeypatch.setattr(service_update_check, "_remote_commit", lambda *_args, **_kwargs: ("b" * 40, None))

    with patch("api.service_update_check.Path.exists", return_value=False):
        response = _client().get("/api/v2/services/agent-core/update-check")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "missing_checkout"
    assert data["remote_commit"] == "bbbbbbbbbbbb"
    assert data["update_available"] is True


def test_update_check_reports_up_to_date(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    monkeypatch.setattr(service_update_check, "_resolve_branch", lambda *_args, **_kwargs: ("main", None))
    monkeypatch.setattr(service_update_check, "_remote_commit", lambda *_args, **_kwargs: ("a" * 40, None))
    monkeypatch.setattr(service_update_check, "_git_commit", lambda *_args, **_kwargs: "a" * 40)

    with patch("api.service_update_check.Path.exists", return_value=True):
        with patch("api.service_update_check.Path.is_dir", return_value=True):
            response = _client().get("/api/v2/services/agent-core/update-check")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "up_to_date"
    assert data["local_commit"] == "aaaaaaaaaaaa"
    assert data["remote_commit"] == "aaaaaaaaaaaa"
    assert data["update_available"] is False


def test_update_check_reports_update_available(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    monkeypatch.setattr(service_update_check, "_resolve_branch", lambda *_args, **_kwargs: ("main", None))
    monkeypatch.setattr(service_update_check, "_remote_commit", lambda *_args, **_kwargs: ("b" * 40, None))
    monkeypatch.setattr(service_update_check, "_git_commit", lambda *_args, **_kwargs: "a" * 40)

    with patch("api.service_update_check.Path.exists", return_value=True):
        with patch("api.service_update_check.Path.is_dir", return_value=True):
            response = _client().get("/api/v2/services/agent-core/update-check")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "update_available"
    assert data["local_commit"] == "aaaaaaaaaaaa"
    assert data["remote_commit"] == "bbbbbbbbbbbb"
    assert data["update_available"] is True


def test_update_check_sanitizes_remote_error(monkeypatch):
    secret = "unit-test-secret"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setattr(service_update_check, "_resolve_branch", lambda *_args, **_kwargs: ("main", None))
    monkeypatch.setattr(service_update_check, "_remote_commit", lambda *_args, **_kwargs: ("", f"bad token {secret}"))

    response = _client().get("/api/v2/services/agent-core/update-check")

    assert response.status_code == 200
    assert secret not in response.text
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "remote_check_failed"
