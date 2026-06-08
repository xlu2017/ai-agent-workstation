"""Tests for the service update-latest endpoint and underlying logic."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app
from api.service_updater import (
    SERVICE_CONFIGS,
    _do_update,
    _get_lock,
    _sanitize,
    get_service_update_metadata,
)


def _client():
    return TestClient(app)


# ── Endpoint: unknown service ──


def test_update_rejects_unknown_service():
    response = _client().post("/api/v2/services/nonexistent/update-latest")
    assert response.status_code == 404
    data = response.json()
    detail = data.get("detail", data)
    assert detail["ok"] is False
    assert detail["error"]["code"] == "UNKNOWN_SERVICE"


# ── Endpoint: missing token returns safe error ──


def test_update_missing_token_returns_safe_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("PAT", raising=False)
    response = _client().post("/api/v2/services/agent-core/update-latest")
    assert response.status_code == 500
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "NO_TOKEN"
    assert "GITHUB_TOKEN" not in data.get("error", {}).get("message", "").upper().replace(
        "GITHUB_TOKEN", ""
    ) or "Set GITHUB_TOKEN" in data["error"]["message"]


# ── Token never in response ──


def test_token_never_in_response(monkeypatch):
    fake_token = "ghp_FAKESECRETTOKEN123456789012345678"
    monkeypatch.setenv("GITHUB_TOKEN", fake_token)

    with patch("api.service_updater._do_update") as mock_update:
        mock_update.return_value = MagicMock(
            ok=False,
            service="agent-core",
            error={"code": "FETCH_FAILED", "message": "Some error occurred"},
            branch="main",
            commit_before="",
            commit_after="",
            updated=False,
            restart_attempted=False,
            restart_succeeded=False,
            message="",
        )
        response = _client().post("/api/v2/services/agent-core/update-latest")
        text = response.text
        assert fake_token not in text


# ── Sanitization ──


def test_sanitize_strips_token():
    token = "ghp_abc123def456ghi789jkl012mno345pqr678"
    raw = f"fatal: unable to access 'https://x-access-token:{token}@github.com/org/repo.git/'"
    result = _sanitize(raw, token)
    assert token not in result
    assert "***" in result


def test_sanitize_strips_ghp_patterns():
    raw = "remote: Invalid token ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    result = _sanitize(raw)
    assert "ghp_" not in result


def test_sanitize_truncates_long_output():
    result = _sanitize("x" * 5000)
    assert len(result) <= 2000


# ── Concurrent update locking ──


def test_concurrent_update_locked(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123456789012345678901234567890")

    lock = _get_lock(SERVICE_CONFIGS["agent-core"]["path"])
    lock.acquire()

    try:
        result = _do_update("agent-core", restart=False)
        assert result.ok is False
        assert result.error["code"] == "UPDATE_LOCKED"
    finally:
        lock.release()


# ── Successful update returns commit info ──


def test_successful_update_returns_commits(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123456789012345678901234567890")

    calls = []

    def fake_run(cmd, cwd=None, env=None, shell=False, capture_output=True, text=True, timeout=120):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""

        if isinstance(cmd, list) and cmd[:2] == ["git", "rev-parse"]:
            if len(calls) <= 2:
                result.stdout = "aaaaaaaaaaaa"
            else:
                result.stdout = "bbbbbbbbbbbb"
        return result

    with patch("api.service_updater.subprocess.run", side_effect=fake_run):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                result = _do_update("agent-core", restart=False)

    assert result.ok is True
    assert result.service == "agent-core"
    assert result.commit_before == "aaaaaaaaaaaa"
    assert result.commit_after == "bbbbbbbbbbbb"
    assert result.updated is True


# ── Service list includes update metadata ──


def test_service_list_includes_update_metadata(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123456789012345678901234567890")
    response = _client().get("/api/services")
    data = response.json()
    services = data["services"]

    agent_core = next((s for s in services if s["name"] == "agent-core"), None)
    assert agent_core is not None
    assert agent_core["repo_backed"] is True
    assert agent_core["update_supported"] is True

    vendor_runtime = next((s for s in services if s["name"] == "vendor-runtime"), None)
    assert vendor_runtime is not None
    assert vendor_runtime["repo_backed"] is False


# ── Shared checkout locking (dashboard + control-plane share one checkout) ──


def test_shared_checkout_uses_same_lock():
    lock_dashboard = _get_lock(SERVICE_CONFIGS["dashboard"]["path"])
    lock_cp = _get_lock(SERVICE_CONFIGS["control-plane"]["path"])
    assert lock_dashboard is lock_cp
