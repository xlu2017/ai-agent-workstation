import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.repo_provider import list_accessible_repositories  # noqa: E402
from api.routes.repo_provider import repo_provider_repositories  # noqa: E402


def test_list_accessible_repositories_reports_missing_token(monkeypatch, tmp_path):
    monkeypatch.setenv("REPO_PROVIDER_CONFIG_PATH", str(tmp_path / "repo-provider.json"))
    monkeypatch.setenv("REPO_PROVIDER_SECRETS_PATH", str(tmp_path / "repo-provider-secrets.json"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("PAT", raising=False)

    result = list_accessible_repositories()

    assert result["ok"] is False
    assert result["repositories"] == []
    assert result["error"]["code"] == "NO_GITHUB_TOKEN"


def test_repo_provider_repositories_route_is_debug_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("REPO_PROVIDER_CONFIG_PATH", str(tmp_path / "repo-provider.json"))
    monkeypatch.setenv("REPO_PROVIDER_SECRETS_PATH", str(tmp_path / "repo-provider-secrets.json"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("PAT", raising=False)

    result = repo_provider_repositories()

    assert "repositories" in result
    assert "access_token" not in str(result)
