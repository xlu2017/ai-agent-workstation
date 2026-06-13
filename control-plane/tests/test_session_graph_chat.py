import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402


def _client(tmp_path: Path) -> TestClient:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    return TestClient(app)


def _create_goal_session(client: TestClient, session_id: str = "goal-chat", repo_session_id: str | None = None) -> dict[str, object]:
    metadata = {"repo_session_id": repo_session_id} if repo_session_id else {}
    response = client.post(
        "/api/session-graph/sessions",
        json={"id": session_id, "kind": "goal", "title": "Graph chat goal", "status": "active", "metadata": metadata},
    )
    assert response.status_code == 200
    return response.json()["session"]


def test_graph_session_chat_appends_user_turn_and_creates_work_session(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(
        f"/api/session-graph/sessions/{session['id']}/chat",
        json={"content": "Continue with the next implementation step.", "mode": "finite"},
    )

    assert response.status_code == 200
    body = response.json()
    next_session = body["session"]
    work_session = body["work_session"]
    assert body["routing_decision"]["route"] == "continue_active"
    assert next_session["state"]["chat_turns"][-1]["role"] == "user"
    assert next_session["metadata"]["graph_chat_status"] == "continue_active"
    assert body["chat_status"] == "needs_repo"
    assert body["execution_state"] == "blocked_needs_repo"
    assert body["auto_started"] is False
    assert work_session["kind"] == "work"
    assert work_session["status"] == "blocked"
    assert work_session["state"]["execution_state"] == "blocked_needs_repo"
    assert work_session["facets"]["work"]["requires_execution_start"] is False
    assert work_session["parent_id"] == session["id"]
    assert body["created_edge"]["type"] == "component_of"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "work.started"]
    assert body["events"][-1]["data"]["auto_started"] is False

    events_response = client.get(f"/api/session-graph/events?session_id={work_session['id']}")
    assert events_response.status_code == 200
    event_types = [event["type"] for event in events_response.json()["events"]]
    assert "work.started" in event_types


def test_graph_session_chat_marks_work_ready_when_repo_is_attached(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client, repo_session_id="repo-context")

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Run validation."})

    assert response.status_code == 200
    body = response.json()
    assert body["chat_status"] == "ready"
    assert body["execution_state"] == "ready_for_execution"
    assert body["auto_started"] is False
    assert body["work_session"]["status"] == "active"
    assert body["work_session"]["state"]["execution_state"] == "ready_for_execution"
    assert body["work_session"]["facets"]["work"]["requires_execution_start"] is True
    assert body["work_session"]["facets"]["work"]["requires_repo"] is False


def test_graph_session_chat_question_only_does_not_create_work(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Why is this a work session?"})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "question_only"
    assert "work_session" not in body
    assert body["chat_status"] == "question_only"
    assert body["execution_state"] == "question_only"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "observation.recorded"]


def test_graph_session_chat_can_create_child_goal(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Create a child task to audit settings."})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "create_child_goal"
    assert body["execution_state"] == "create_child_goal"
    assert body["goal_session"]["kind"] == "goal"
    assert body["goal_session"]["parent_id"] == session["id"]
    assert body["created_edge"]["type"] == "component_of"


def test_graph_session_chat_can_create_sibling_goal(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Start a new session for billing docs."})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "create_sibling_goal"
    assert body["execution_state"] == "create_sibling_goal"
    assert body["goal_session"]["kind"] == "goal"
    assert body["goal_session"]["parent_id"] is None
    assert body["created_edge"]["type"] == "sibling_of"


def test_graph_session_chat_rejects_empty_messages(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "   "})
    assert response.status_code == 400
