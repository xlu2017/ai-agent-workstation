"""Tests for repo-backed service update-latest behavior."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api import service_updater  # noqa: E402
from api.service_updater import (  # noqa: E402
    SERVICE_CONFIGS,
    _do_update,
    _get_lock,
    _resolve_branch,
    _sanitize,
)


def _client():
    return TestClient(app)


def _with_branch(monkeypatch, service_name: str = "agent-core"):
    config = {**SERVICE_CONFIGS[service_name], "branch": "main"}
    monkeypatch.setitem(SERVICE_CONFIGS, service_name, config)
    return config


def test_update_rejects_unknown_service():
    response = _client().post("/api/v2/services/nonexistent/update-latest")
    assert response.status_code == 404
    data = response.json()
    detail = data.get("detail", data)
    assert detail["ok"] is False
    assert detail["error"]["code"] == "UNKNOWN_SERVICE"


def test_update_missing_token_returns_safe_error(monkeypatch):
    _with_branch(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("PAT", raising=False)

    response = _client().post("/api/v2/services/agent-core/update-latest")

    assert response.status_code == 500
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "NO_TOKEN"
    assert "Set GITHUB_TOKEN" in data["error"]["message"]


def test_token_never_in_response(monkeypatch):
    secret = "unit-test-secret-value"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    _with_branch(monkeypatch)

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
        assert secret not in response.text


def test_sanitize_strips_token_and_auth_url():
    token = "unit-test-secret-value"
    raw = f"fatal: unable to access 'https://x-access-token:{token}@github.com/org/repo.git/'"
    result = _sanitize(raw, token)
    assert token not in result
    assert "x-access-token:" not in result
    assert "***" in result


def test_sanitize_truncates_long_output():
    result = _sanitize("x" * 5000)
    assert len(result) <= 2500


def test_configured_branch_does_not_call_git(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise AssertionError("git should not be called when branch is configured")

    monkeypatch.setattr(service_updater, "_run_cmd", fail_run)

    branch, error = _resolve_branch("https://github.com/xlu2017/ai-agent-workstation.git", "main", "token")

    assert branch == "main"
    assert error is None


def test_default_branch_resolves_from_remote_head(monkeypatch):
    result = MagicMock(returncode=0, stdout="ref: refs/heads/trunk\tHEAD\n", stderr="")
    monkeypatch.setattr(service_updater, "_run_cmd", lambda *_args, **_kwargs: result)

    branch, error = _resolve_branch("https://github.com/xlu2017/ai-agent-workstation.git", None, "token")

    assert branch == "trunk"
    assert error is None


def test_update_status_persists_to_disk(tmp_path, monkeypatch):
    status_path = tmp_path / "service-updates.json"
    monkeypatch.setattr(service_updater, "UPDATE_STATUS_PATH", status_path)
    service_updater.clear_update_status("dashboard")

    service_updater.set_update_status("dashboard", {
        "in_progress": False,
        "last_update": {"status": "success", "message": "updated"},
    })

    status = service_updater.get_update_status("dashboard")
    assert status is not None
    assert status["last_update"]["status"] == "success"
    assert status_path.exists()


def test_concurrent_update_locked(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    config = _with_branch(monkeypatch)

    lock = _get_lock(config["path"])
    lock.acquire()

    try:
        result = _do_update("agent-core", restart=False)
        assert result.ok is False
        assert result.error["code"] == "UPDATE_LOCKED"
    finally:
        lock.release()


def test_successful_update_returns_commits(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    _with_branch(monkeypatch)

    calls = []

    def fake_run(cmd, cwd=None, env=None, shell=False, capture_output=True, text=True, timeout=120):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if isinstance(cmd, list) and cmd[:2] == ["git", "rev-parse"]:
            rev_parse_count = len([c for c in calls if isinstance(c, list) and c[:2] == ["git", "rev-parse"]])
            result.stdout = "aaaaaaaaaaaa" if rev_parse_count == 1 else "bbbbbbbbbbbb"
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
    assert result.steps is not None
    assert any(step["phase"] == "fetch" for step in result.steps)


def test_missing_checkout_runs_clone_then_install_and_build(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    config = {**SERVICE_CONFIGS["agent-core"], "branch": "main", "install_commands": ["install-cmd"], "build_commands": ["build-cmd"]}
    monkeypatch.setitem(SERVICE_CONFIGS, "agent-core", config)
    exists_values = iter([False])

    def fake_exists(_self):
        return next(exists_values, True)

    calls = []

    def fake_run(cmd, cwd=None, env=None, shell=False, capture_output=True, text=True, timeout=120):
        calls.append(cmd)
        result = MagicMock(returncode=0, stdout="", stderr="")
        if isinstance(cmd, list) and cmd[:2] == ["git", "rev-parse"]:
            result.stdout = "cccccccccccc"
        return result

    monkeypatch.setattr(Path, "exists", fake_exists)
    with patch("api.service_updater.subprocess.run", side_effect=fake_run):
        result = _do_update("agent-core", restart=False)

    assert result.ok is True
    assert any(isinstance(cmd, list) and cmd[:2] == ["git", "clone"] for cmd in calls)
    assert "install-cmd" in calls
    assert "build-cmd" in calls


def test_service_list_includes_update_metadata(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
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


def test_shared_checkout_uses_same_lock():
    lock_dashboard = _get_lock(SERVICE_CONFIGS["dashboard"]["path"])
    lock_cp = _get_lock(SERVICE_CONFIGS["control-plane"]["path"])
    assert lock_dashboard is lock_cp
