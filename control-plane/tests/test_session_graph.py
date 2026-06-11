import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app


def _client(tmp_path: Path) -> TestClient:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    return TestClient(app)


def _create_session(client: TestClient, session_id: str, kind: str, title: str, facets: dict[str, dict[str, object]] | None = None):
    response = client.post("/api/session-graph/sessions", json={
        "id": session_id,
        "kind": kind,
        "title": title,
        "summary": f"{title} summary",
        "facets": facets or {},
    })
    assert response.status_code == 200
    return response.json()["session"]


def test_mount_repo_under_app_session(tmp_path: Path):
    client = _client(tmp_path)
    repo = _create_session(client, "repo-agent-core", "repo", "agent-core")
    app_session = _create_session(client, "app-agent-platform", "app", "Agent Platform")

    response = client.post("/api/session-graph/mount", json={
        "source_session_id": repo["id"],
        "target_session_id": app_session["id"],
        "user_intent": "Compose repo into app session.",
        "mount_mode": "component",
        "create_adaptation_session": True,
    })

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["mounted_edge"]["type"] == "mounted_under"
    assert result["adaptation_session"]["kind"] == "adapter"


def test_mount_openhands_under_integration_goal(tmp_path: Path):
    client = _client(tmp_path)
    source = _create_session(client, "repo-openhands", "repo", "OpenHands", {
        "repo": {
            "capabilities": [
                "shell execution",
                "browser interaction",
                "file editing",
                "agent loop",
                "task completion detection",
                "cancellation handling",
            ]
        }
    })
    target = _create_session(client, "goal-openhands", "goal", "Integrate OpenHands executor functionality")

    response = client.post("/api/session-graph/mount", json={
        "source_session_id": source["id"],
        "target_session_id": target["id"],
        "user_intent": "Adapt executor behavior into platform.",
        "mount_mode": "reference",
        "create_adaptation_session": True,
    })

    assert response.status_code == 200
    result = response.json()["result"]
    adapter = result["adaptation_session"]["facets"]["adapter"]
    assert adapter["source_role"] == "reference_implementation"
    assert adapter["target_role"] == "capability_to_integrate"
    assert adapter["preservation_mode"] == "lossless_reference"
    assert adapter["adaptation_mode"] == "capability_mapping"
    assert len(adapter["mappings"]) >= 6


def test_preview_mount_warns_for_broad_source_under_tiny_target(tmp_path: Path):
    client = _client(tmp_path)
    _create_session(client, "repo-openhands", "repo", "OpenHands")
    _create_session(client, "goal-looping", "goal", "Make my executor stop looping")

    response = client.post("/api/session-graph/mount/preview", json={
        "source_session_id": "repo-openhands",
        "target_session_id": "goal-looping",
        "user_intent": "Use only loop termination behavior.",
        "mount_mode": "unknown",
        "create_adaptation_session": True,
    })

    assert response.status_code == 200
    result = response.json()["result"]
    assert any("broader than target" in warning for warning in result["warnings"])
    assert "deployment" in result["context_projection_delta"]["exclude_selectors"]

    snapshot = client.get("/api/session-graph/snapshot").json()["graph"]
    assert snapshot["edges"] == []


def test_applied_mount_persists_edge_event_and_projection_without_mutating_source(tmp_path: Path):
    client = _client(tmp_path)
    _create_session(client, "repo-openhands", "repo", "OpenHands")
    before = client.get("/api/session-graph/sessions/repo-openhands").json()["session"]
    _create_session(client, "goal-looping", "goal", "Make my executor stop looping")

    response = client.post("/api/session-graph/mount", json={
        "source_session_id": "repo-openhands",
        "target_session_id": "goal-looping",
        "user_intent": "Use only loop termination behavior.",
        "mount_mode": "reference",
        "create_adaptation_session": True,
    })

    assert response.status_code == 200
    after = client.get("/api/session-graph/sessions/repo-openhands").json()["session"]
    assert after == before
    snapshot = client.get("/api/session-graph/snapshot").json()["graph"]
    assert len(snapshot["edges"]) >= 3
    assert any(event["type"] == "session.mounted" for event in snapshot["events"])
    assert len(snapshot["projections"]) == 1


def test_apply_session_update_proposal_persists_graph_changes(tmp_path: Path):
    client = _client(tmp_path)
    response = client.post("/api/session-graph/session-update/apply", json={
        "classification": "create_child",
        "active_session_id": "goal-open-terminal",
        "created_sessions": [{
            "id": "goal-open-terminal",
            "kind": "goal",
            "title": "open terminal flow",
        }, {
            "id": "work-backend-terminal",
            "kind": "work",
            "title": "backend terminal endpoint",
        }],
        "created_edges": [{
            "type": "component_of",
            "source_session_id": "work-backend-terminal",
            "target_session_id": "goal-open-terminal",
        }],
        "reason": "Track backend terminal work separately.",
    })

    assert response.status_code == 200
    graph = response.json()["graph"]
    assert graph["sessions"][1]["id"] == "work-backend-terminal"
    assert graph["edges"][0]["type"] == "component_of"
