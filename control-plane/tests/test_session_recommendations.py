import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_recommend_next_route_forwards_ambient_context(monkeypatch):
    from ambient.event_log import persist_ambient_event
    from ambient.types import AmbientEvent, AmbientSource
    from api.routes import session_recommendations
    import agent_core_client.client as agent_client_module

    class FakeAgentCoreClient:
        last_call = {}

        async def recommend_next(
            self,
            *,
            task_type,
            current_action,
            completed_actions,
            session_id,
            repo_id,
            ambient_context=None,
            suggested_plan=None,
        ):
            FakeAgentCoreClient.last_call = {
                "task_type": task_type,
                "current_action": current_action,
                "completed_actions": completed_actions,
                "session_id": session_id,
                "repo_id": repo_id,
                "ambient_context": ambient_context,
                "suggested_plan": suggested_plan,
            }
            return {"ok": True, "next_action": {"action_name": "read_file"}}

        async def close(self):
            return None

    monkeypatch.setattr(agent_client_module, "AgentCoreClient", FakeAgentCoreClient)

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(session_recommendations, "SESSIONS_DIR", Path(tmpdir))
        event = AmbientEvent(
            event_type="browser.element_selected",
            session_id="s1",
            source=AmbientSource.BROWSER,
            actor="user",
            confidence=0.91,
            payload={
                "selection": {
                    "elements": [
                        {
                            "selector": "[data-testid=save]",
                            "componentName": "SaveButton",
                            "sourceFile": "src/components/SaveButton.tsx",
                            "sourceLine": 12,
                            "sourceConfidence": 0.93,
                        }
                    ]
                }
            },
        )
        persist_ambient_event(event, sessions_dir=tmpdir)

        app = FastAPI()
        app.include_router(session_recommendations.router)
        client = TestClient(app)

        response = client.post(
            "/api/sessions/s1/recommendations/next-action",
            json={
                "task_type": "implementation",
                "current_action": "fix selected component",
                "completed_actions": ["browser.element_selected"],
                "repo_id": "repo-1",
                "suggested_plan": {"steps": [{"action_name": "read_file"}]},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["advisory_only"] is True
    assert body["requires_platform_validation"] is True
    assert body["recommendation"]["ok"] is True
    assert body["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert "src/components/SaveButton.tsx:12" in body["prompt_block"]
    assert FakeAgentCoreClient.last_call["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert FakeAgentCoreClient.last_call["suggested_plan"]["steps"][0]["action_name"] == "read_file"
