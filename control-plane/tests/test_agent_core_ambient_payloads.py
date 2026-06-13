import asyncio
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_agent_core_client_forwards_ambient_context_to_recommend_next(monkeypatch):
    import agent_core_client.client as client_module
    from agent_core_client.client import AgentCoreClient

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    client = AgentCoreClient(base_url="http://agent-core.test")
    response = asyncio.run(client.recommend_next(
        task_type="implementation",
        current_action="fix selected component",
        completed_actions=["browser.element_selected"],
        session_id="s1",
        repo_id="repo-1",
        ambient_context={"source_candidates": [{"path": "src/components/SaveButton.tsx"}]},
    ))

    assert response["ok"] is True
    assert fake_client.posts[0]["path"] == "/actions/recommend-next"
    payload = fake_client.posts[0]["json"]
    assert payload["task_type"] == "implementation"
    assert payload["current_action"] == "fix selected component"
    assert payload["completed_actions"] == ["browser.element_selected"]
    assert payload["context"]["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert "suggested_plan" not in payload["context"]


def test_agent_core_client_can_forward_suggested_plan_only_for_non_execution_compatibility(monkeypatch):
    import agent_core_client.client as client_module
    from agent_core_client.client import AgentCoreClient

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    client = AgentCoreClient(base_url="http://agent-core.test")
    asyncio.run(client.recommend_next(
        task_type="implementation",
        current_action="fix selected component",
        completed_actions=[],
        session_id="s1",
        repo_id="repo-1",
        suggested_plan={"display_only": True},
    ))

    payload = fake_client.posts[0]["json"]
    assert payload["context"]["suggested_plan"] == {"display_only": True}


class FakeResponse:
    def json(self):
        return {"ok": True, "next_action": {"action_name": "read_file", "params": {"path": "x.py"}}}

    def raise_for_status(self):
        return None


class FakeAsyncClient:
    def __init__(self):
        self.posts = []

    async def post(self, path, json):
        self.posts.append({"path": path, "json": json})
        return FakeResponse()

    async def aclose(self):
        return None
