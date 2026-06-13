import asyncio
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_agent_core_client_forwards_ambient_context_to_plan(monkeypatch):
    import agent_core_client.client as client_module
    from agent_core_client.client import AgentCoreClient, PlanRequest

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: fake_client)

    client = AgentCoreClient(base_url="http://agent-core.test")
    response = asyncio.run(client.plan(PlanRequest(
        session_id="s1",
        repo_id="repo-1",
        prompt="fix selected component",
        allowed_actions=["read_file"],
        ambient_context={
            "source_candidates": [{"path": "src/components/SaveButton.tsx", "confidence": 0.93}],
            "advisory_only": True,
            "requires_platform_validation": True,
        },
    )))

    assert response["ok"] is True
    assert fake_client.posts[0]["path"] == "/actions/plan"
    payload = fake_client.posts[0]["json"]
    assert payload["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert payload["ambient_context"]["requires_platform_validation"] is True


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
        suggested_plan={"steps": [{"action_name": "read_file"}]},
    ))

    assert response["ok"] is True
    assert fake_client.posts[0]["path"] == "/actions/recommend-next"
    payload = fake_client.posts[0]["json"]
    assert payload["context"]["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert payload["context"]["suggested_plan"]["steps"][0]["action_name"] == "read_file"


class FakeResponse:
    def json(self):
        return {"ok": True}

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
