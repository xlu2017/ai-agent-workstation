import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.session_graph import router as session_graph_router  # noqa: E402
from api.session_graph_overview import router as overview_router  # noqa: E402


def _client(tmp_path: Path) -> TestClient:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    app = FastAPI()
    app.include_router(session_graph_router)
    app.include_router(overview_router)
    return TestClient(app)


def test_session_graph_overview_counts_created_and_mounted_sessions(tmp_path: Path):
    client = _client(tmp_path)

    repo = client.post("/api/session-graph/sessions", json={
        "id": "repo",
        "kind": "repo",
        "title": "Repo",
        "summary": "Reference repository",
    })
    assert repo.status_code == 200

    goal = client.post("/api/session-graph/sessions", json={
        "id": "goal",
        "kind": "goal",
        "title": "Goal",
        "summary": "Focused integration goal",
    })
    assert goal.status_code == 200

    mount = client.post("/api/session-graph/mount", json={
        "source_session_id": "repo",
        "target_session_id": "goal",
        "user_intent": "Use relevant repo behavior in this goal.",
        "mount_mode": "reference",
        "create_adaptation_session": True,
        "make_active": False,
    })
    assert mount.status_code == 200

    overview = client.get("/api/session-graph/overview")
    assert overview.status_code == 200
    data = overview.json()

    assert data["sessions"]["total"] == 3
    assert data["sessions"]["by_kind"]["repo"] == 1
    assert data["sessions"]["by_kind"]["goal"] == 1
    assert data["sessions"]["by_kind"]["adapter"] == 1
    assert data["edges"]["by_type"]["mounted_under"] == 1
    assert data["projections"]["total"] == 1
    assert data["projections"]["total_budget"]["max_tokens"] == 4000
    assert data["events"]["latest"] is not None


def test_session_graph_overview_respects_workspace_scope(tmp_path: Path):
    client = _client(tmp_path)

    default = client.post("/api/session-graph/sessions", json={
        "id": "default-goal",
        "kind": "goal",
        "title": "Default Goal",
    })
    assert default.status_code == 200

    other = client.post(
        "/api/session-graph/sessions",
        headers={"X-Workspace-Id": "other"},
        json={
            "id": "other-goal",
            "kind": "goal",
            "title": "Other Goal",
        },
    )
    assert other.status_code == 200

    default_overview = client.get("/api/session-graph/overview")
    other_overview = client.get("/api/session-graph/overview", headers={"X-Workspace-Id": "other"})

    assert default_overview.status_code == 200
    assert other_overview.status_code == 200
    assert default_overview.json()["sessions"]["total"] == 1
    assert other_overview.json()["sessions"]["total"] == 1
