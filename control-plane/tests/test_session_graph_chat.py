import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402


def _client(tmp_path: Path) -> TestClient:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    return TestClient(app)


def _create_goal_session(client: TestClient, session_id: str = "goal-chat") -> dict[str, object]:
    response = client.post(
        "/api/session-graph/sessions",
        json={"id": session_id, "kind": "goal", "title": "Graph chat goal", "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["session"]


def test_graph_session_chat_appends_user_turn_and_events(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(
        f"/api/session-graph/sessions/{session['id']}/chat",
        json={"content": "Continue with the next implementation step.", "execution_mode": "finite"},
    )

    assert response.status_code == 200
    body = response.json()
    next_session = body["session"]
    assert next_session["state"]["chat_turns"][-1]["role"] == "user"
    assert next_session["state"]["chat_turns"][-1]["content"] == "Continue with the next implementation step."
    assert next_session["metadata"]["graph_chat_execution_bridge"] == "not_wired"
    assert body["execution_bridge_status"] == "not_wired"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "action.proposed"]

    events_response = client.get(f"/api/session-graph/events?session_id={session['id']}")
    assert events_response.status_code == 200
    event_types = [event["type"] for event in events_response.json()["events"]]
    assert "user.interjected" in event_types
    assert "action.proposed" in event_types


def test_graph_session_chat_rejects_empty_messages(tmp_path: Path):
    client = _client(tmp_path)
    session = _create_goal_session(client)

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "   "})

    assert response.status_code == 400
