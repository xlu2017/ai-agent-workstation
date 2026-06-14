import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes.session_graph import chat as chat_route  # noqa: E402
from api.server import app  # noqa: E402
from api.services.session_graph_prompt_recommendation import PromptRoutingUnavailable  # noqa: E402


def test_graph_chat_returns_503_when_prompt_routing_is_unavailable(tmp_path: Path, monkeypatch):
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    client = TestClient(app)

    response = client.post(
        "/api/session-graph/sessions",
        json={"id": "goal-routing-error", "kind": "goal", "title": "Routing error", "status": "active"},
    )
    assert response.status_code == 200

    def unavailable(*_args, **_kwargs):
        raise PromptRoutingUnavailable("agent-core unavailable")

    monkeypatch.setattr(chat_route, "recommend_graph_prompt_route", unavailable)

    response = client.post(
        "/api/session-graph/sessions/goal-routing-error/chat",
        json={"content": "Continue."},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "prompt_routing_unavailable"

    graph_response = client.get("/api/session-graph/sessions/goal-routing-error")
    assert graph_response.status_code == 200
    session = graph_response.json()["session"]
    assert session["state"].get("chat_turns") in (None, [])
