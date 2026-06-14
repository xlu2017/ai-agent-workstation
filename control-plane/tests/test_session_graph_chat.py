import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes.session_graph import chat as chat_route  # noqa: E402
from api.server import app  # noqa: E402
from api.services.session_graph_prompt_recommendation import PromptRouteRecommendation  # noqa: E402


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


def _stub_prompt_routing(monkeypatch, *, route: str, reason: str = "test route", assistant_response: str = "", narration: str = "") -> None:
    def route_prompt(session, prompt):
        return PromptRouteRecommendation(
            route=route,
            reason=reason,
            source="test_stub",
            payload={},
            assistant_response=assistant_response,
            response_session_kind="chat" if route == "question_only" else "",
            narration=narration,
        )

    monkeypatch.setattr(chat_route, "recommend_graph_prompt_route", route_prompt)


def test_graph_session_chat_appends_user_turn_and_creates_work_session(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client)
    _stub_prompt_routing(monkeypatch, route="continue_active")

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
    assert body["execution_readiness"]["status"] == "blocked_needs_repo"
    assert body["execution_readiness"]["auto_started"] is False
    assert work_session["kind"] == "work"
    assert work_session["status"] == "blocked"
    assert work_session["state"]["execution_state"] == "blocked_needs_repo"
    assert work_session["state"]["execution_readiness"]["status"] == "blocked_needs_repo"
    assert work_session["facets"]["work"]["requires_execution_start"] is False
    assert work_session["facets"]["work"]["execution_readiness"]["auto_started"] is False
    assert work_session["parent_id"] == session["id"]
    assert body["created_edge"]["type"] == "component_of"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "work.execution_readiness_recorded"]
    assert body["events"][-1]["data"]["auto_started"] is False
    assert body["events"][-1]["data"]["execution_readiness"]["auto_started"] is False

    events_response = client.get(f"/api/session-graph/events?session_id={work_session['id']}")
    assert events_response.status_code == 200
    event_types = [event["type"] for event in events_response.json()["events"]]
    assert "work.execution_readiness_recorded" in event_types


def test_graph_session_chat_marks_work_ready_when_repo_is_attached(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client, repo_session_id="repo-context")
    _stub_prompt_routing(monkeypatch, route="continue_active")

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Run validation."})

    assert response.status_code == 200
    body = response.json()
    assert body["chat_status"] == "ready"
    assert body["execution_state"] == "ready_for_execution"
    assert body["auto_started"] is False
    assert body["execution_readiness"]["status"] == "ready_not_started"
    assert body["execution_readiness"]["auto_started"] is False
    assert body["execution_readiness"]["initial_execution_scaffold"]["executor_start"]["status"] == "pending_adapter"
    assert body["work_session"]["status"] == "active"
    assert body["work_session"]["state"]["execution_state"] == "ready_for_execution"
    assert body["work_session"]["state"]["execution_readiness"]["status"] == "ready_not_started"
    assert body["work_session"]["facets"]["work"]["requires_execution_start"] is True
    assert body["work_session"]["facets"]["work"]["requires_repo"] is False
    assert body["work_session"]["facets"]["work"]["execution_readiness"]["auto_started"] is False
    assert [event["type"] for event in body["events"]] == ["user.interjected", "work.execution_readiness_recorded"]


def test_graph_session_chat_question_only_answers_without_work_when_no_repo_context(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client)
    _stub_prompt_routing(monkeypatch, route="question_only", assistant_response="This is a chat response.")

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Why is this a work session?"})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "question_only"
    assert "work_session" not in body
    assert "execution_readiness" not in body
    assert "execution_activation" not in body
    assert "question_session" not in body
    assert body["chat_status"] == "answered"
    assert body["execution_state"] == "answered_inline"
    assert body["assistant_turn"]["role"] == "assistant"
    assert body["chat_session"]["kind"] == "chat"
    assert body["chat_session"]["status"] == "completed"
    assert body["chat_session"]["facets"]["chat"]["non_executable"] is True
    assert body["chat_session"]["state"]["auto_started"] is False
    assert body["events"][-1]["data"]["response_session_kind"] == "chat"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "observation.recorded"]


def test_graph_session_chat_repo_context_question_routes_to_work_before_answering(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client, repo_session_id="game-repo-context")
    _stub_prompt_routing(monkeypatch, route="continue_active")

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Why is the world round?"})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "continue_active"
    assert body["chat_status"] == "ready"
    assert body["execution_state"] == "ready_for_execution"
    assert "assistant_turn" not in body
    assert "chat_session" not in body
    assert "question_session" not in body
    assert body["work_session"]["kind"] == "work"
    assert body["work_session"]["facets"]["work"]["requires_execution_start"] is True
    assert body["execution_readiness"]["status"] == "ready_not_started"
    assert body["execution_readiness"]["initial_execution_scaffold"]["steps"][0]["task_name"] == "search_code"
    assert [event["type"] for event in body["events"]] == ["user.interjected", "work.execution_readiness_recorded"]


def test_graph_session_chat_can_create_child_goal(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client)
    _stub_prompt_routing(monkeypatch, route="create_child_goal")

    response = client.post(f"/api/session-graph/sessions/{session['id']}/chat", json={"content": "Create a child task to audit settings."})

    assert response.status_code == 200
    body = response.json()
    assert body["routing_decision"]["route"] == "create_child_goal"
    assert body["execution_state"] == "create_child_goal"
    assert body["goal_session"]["kind"] == "goal"
    assert body["goal_session"]["parent_id"] == session["id"]
    assert body["created_edge"]["type"] == "component_of"


def test_graph_session_chat_can_create_sibling_goal(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    session = _create_goal_session(client)
    _stub_prompt_routing(monkeypatch, route="create_sibling_goal")

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
