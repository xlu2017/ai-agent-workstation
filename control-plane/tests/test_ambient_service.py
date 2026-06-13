import json
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_ambient_service_collects_with_missing_external_services(tmp_path):
    from ambient.config import AmbientCollectorConfig
    from ambient.service import AmbientObservationService

    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    context_dir = session_dir / "context"
    repo_dir = tmp_path / "repos" / "worktree-s1"
    context_dir.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (context_dir / "latest-terminal-context.md").write_text("pytest failed in tests/test_login.py")
    (session_dir / "session.json").write_text(json.dumps({
        "id": "s1",
        "repo_path": str(repo_dir),
        "worktree_path": str(repo_dir),
        "branch": "feature/s1",
    }))

    config = AmbientCollectorConfig(
        sessions_dir=sessions_dir,
        repos_dir=tmp_path / "repos",
        browser_debug_urls=["http://127.0.0.1:9"],
        browser_timeout_seconds=0.01,
        desktop_enabled=False,
        browser_enabled=True,
        repo_enabled=True,
        legacy_context_enabled=True,
    )

    result = AmbientObservationService(config).collect_once("s1", goal="fix this")

    assert result.session_id == "s1"
    assert result.events_persisted >= 2
    assert result.context_packet is not None
    assert result.context_packet.goal == "fix this"
    assert (session_dir / "ambient" / "state.json").exists()
    assert (session_dir / "ambient" / "context_packet.json").exists()
    assert (session_dir / "ambient" / "evidence_graph.json").exists()


def test_ambient_service_collects_from_session_meta_worktree_id(tmp_path):
    from ambient.config import AmbientCollectorConfig
    from ambient.service import AmbientObservationService

    sessions_dir = tmp_path / "sessions"
    repos_dir = tmp_path / "repos"
    session_dir = sessions_dir / "s1"
    repo_dir = repos_dir / "worktree-s1"
    session_dir.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "app.py").write_text("print('hello')\n")
    (session_dir / "session-meta.json").write_text(json.dumps({
        "session_id": "s1",
        "worktree_id": "worktree-s1",
        "repo_id": "repo-1",
        "branch": "feature/s1",
    }))

    config = AmbientCollectorConfig(
        sessions_dir=sessions_dir,
        repos_dir=repos_dir,
        browser_debug_urls=["http://127.0.0.1:9"],
        browser_timeout_seconds=0.01,
        desktop_enabled=False,
        browser_enabled=False,
        repo_enabled=True,
        legacy_context_enabled=False,
    )

    result = AmbientObservationService(config).collect_once("s1", goal="inspect repo")

    statuses = {status.name: status for status in result.statuses}
    assert statuses["repo"].status in {"ok", "degraded"}
    assert statuses["repo"].details["path"] == str(repo_dir)
    assert result.context_packet is not None
    assert result.context_packet.worktree_id == str(repo_dir)
    assert (session_dir / "ambient" / "state.json").exists()
    assert (session_dir / "ambient" / "context_packet.json").exists()
    assert (session_dir / "ambient" / "evidence_graph.json").exists()


def test_ambient_service_health_is_degraded_not_failing(tmp_path):
    from ambient.config import AmbientCollectorConfig
    from ambient.service import AmbientObservationService

    config = AmbientCollectorConfig(
        sessions_dir=tmp_path / "sessions",
        repos_dir=tmp_path / "repos",
        browser_debug_urls=["http://127.0.0.1:9"],
        browser_timeout_seconds=0.01,
    )

    health = AmbientObservationService(config).health()

    assert health["ok"] is True
    assert health["browser"]["status"] in {"available", "unavailable"}
    assert health["config"]["sessions_dir"] == str(config.sessions_dir)
