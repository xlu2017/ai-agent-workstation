"""Tests for service-to-repository source registry."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api import repo_source_registry  # noqa: E402
from api import service_updater  # noqa: E402


def _client():
    return TestClient(app)


def _isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_source_registry, "REGISTRY_PATH", tmp_path / "repo-sources.json")


def test_default_registry_builds_repo_url_from_owner_repo(tmp_path, monkeypatch):
    _isolate_registry(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_CORE_REPO_OWNER", "example")
    monkeypatch.setenv("AGENT_CORE_REPO_NAME", "agent-core-alt")
    monkeypatch.delenv("AGENT_CORE_REPO_URL", raising=False)

    source = repo_source_registry.get_repo_source("agent-core")

    assert source is not None
    assert source["owner"] == "example"
    assert source["repo"] == "agent-core-alt"
    assert source["repo_url"] == "https://github.com/example/agent-core-alt.git"


def test_repo_source_routes_update_owner_repo_and_service_metadata(tmp_path, monkeypatch):
    _isolate_registry(tmp_path, monkeypatch)

    response = _client().put("/api/repo-sources/agent-core", json={
        "owner": "acme",
        "repo": "agent-core-fork",
        "branch": "stable",
        "path": "/srv/agent-core-fork",
        "repo_url": None,
    })

    assert response.status_code == 200
    data = response.json()["service"]
    assert data["owner"] == "acme"
    assert data["repo"] == "agent-core-fork"
    assert data["repo_url"] == "https://github.com/acme/agent-core-fork.git"

    config = service_updater.SERVICE_CONFIGS.get("agent-core")
    assert config["repo_url"] == "https://github.com/acme/agent-core-fork.git"
    assert config["branch"] == "stable"
    assert config["path"] == "/srv/agent-core-fork"


def test_repo_source_can_disable_repo_backed_service(tmp_path, monkeypatch):
    _isolate_registry(tmp_path, monkeypatch)

    response = _client().put("/api/repo-sources/agent-core", json={"enabled": False})

    assert response.status_code == 200
    assert service_updater.SERVICE_CONFIGS.get("agent-core") is None


def test_repo_source_reset_restores_default(tmp_path, monkeypatch):
    _isolate_registry(tmp_path, monkeypatch)
    _client().put("/api/repo-sources/agent-core", json={"owner": "acme", "repo": "changed"})

    response = _client().post("/api/repo-sources/agent-core/reset")

    assert response.status_code == 200
    data = response.json()["service"]
    assert data["service"] == "agent-core"
    assert data["repo_url"].endswith("/agent-core.git")


def test_repo_sources_are_exposed_in_service_list(tmp_path, monkeypatch):
    _isolate_registry(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")

    response = _client().get("/api/services")

    assert response.status_code == 200
    services = response.json()["services"]
    agent_core = next(service for service in services if service["name"] == "agent-core")
    assert agent_core["repo_backed"] is True
    assert agent_core["repo_source"]["repo"] == "agent-core"
