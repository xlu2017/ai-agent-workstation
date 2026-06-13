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


def test_session_controller_plan_request_includes_ambient_context():
    import asyncio

    from ambient.event_log import persist_ambient_event
    from ambient.types import AmbientEvent, AmbientSource
    from sessions.controller import CreateSessionRequest, SessionController

    class FakeAgentCoreClient:
        def __init__(self):
            self.plan_request = None

        async def plan(self, request):
            self.plan_request = request
            return {
                "ok": True,
                "plan": {"mode": "finite", "steps": [{"action_name": "read_file", "params": {"path": "src/components/SaveButton.tsx"}}]},
            }

        async def validate_plan(self, allowed_actions, plan):
            return {"valid": True, "errors": []}

    class FakeWorkflowAdapter:
        def __init__(self):
            self.context = None

        async def start_plan(self, session_id, plan, context):
            self.context = context
            return {"backend": "fake", "workflow_run_id": "wf-1"}

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_core = FakeAgentCoreClient()
        workflow = FakeWorkflowAdapter()
        controller = SessionController(
            sessions_dir=tmpdir,
            agent_core_client=agent_core,
            workflow_adapter=workflow,
        )
        result = controller.create_session(
            CreateSessionRequest(
                prompt="initial",
                repo_id="repo-1",
                allowed_actions=["read_file", "grep", "run_tests"],
            )
        )
        session_id = result["session"]["session_id"]
        event = AmbientEvent(
            event_type="browser.element_selected",
            session_id=session_id,
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
        session = controller.session_store.get(session_id)

        plan_result = asyncio.run(controller._request_and_start_plan(session, "fix selected button"))

        events = controller.event_store.get_events(session_id)

    assert "plan" in plan_result
    assert agent_core.plan_request.ambient_context["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert workflow.context["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert workflow.context["ambient_prompt_context"]
    assert any(event["event_type"] == "plan_requested" and event["data"].get("ambient_context_attached") for event in events)
