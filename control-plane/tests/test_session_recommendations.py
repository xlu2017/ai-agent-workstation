import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_recommend_next_route_forwards_ambient_context(monkeypatch):
    from ambient.event_log import persist_ambient_event
    from api.routes import session_recommendations
    import agent_core_client.client as agent_client_module

    class FakeAgentCoreClient:
        last_call = {}

        async def recommend_next(self, *, task_type, current_action, completed_actions, session_id, repo_id, ambient_context=None):
            FakeAgentCoreClient.last_call = {
                "task_type": task_type,
                "current_action": current_action,
                "completed_actions": completed_actions,
                "session_id": session_id,
                "repo_id": repo_id,
                "ambient_context": ambient_context,
            }
            return {"ok": True, "next_action": {"action_name": "read_file"}}

        async def close(self):
            return None

    monkeypatch.setattr(agent_client_module, "AgentCoreClient", FakeAgentCoreClient)

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(session_recommendations, "SESSIONS_DIR", Path(tmpdir))
        persist_ambient_event(_browser_selection_event("s1"), sessions_dir=tmpdir)

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
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["ok"] is True
    assert body["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert FakeAgentCoreClient.last_call["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"


def test_session_controller_uses_recommend_next_as_execution_source():
    import asyncio

    from ambient.event_log import persist_ambient_event
    from sessions.controller import CreateSessionRequest, SessionController

    class FakeAgentCoreClient:
        def __init__(self):
            self.recommend_next_call = None
            self.validate_action_call = None

        async def recommend_next(self, *, task_type, current_action, completed_actions, session_id, repo_id, ambient_context=None):
            self.recommend_next_call = {
                "task_type": task_type,
                "current_action": current_action,
                "completed_actions": completed_actions,
                "session_id": session_id,
                "repo_id": repo_id,
                "ambient_context": ambient_context,
            }
            return {
                "ok": True,
                "next_action": {
                    "action_name": "read_file",
                    "params": {"path": "src/components/SaveButton.tsx"},
                    "rationale": "Inspect selected component first.",
                },
            }

        async def validate_action(self, action_name, params):
            self.validate_action_call = {"action_name": action_name, "params": params}
            return {"valid": True, "errors": []}

    class FakeWorkflowAdapter:
        def __init__(self):
            self.context = None
            self.plan = None

        async def start_plan(self, session_id, plan, context):
            self.context = context
            self.plan = plan
            return {"backend": "fake", "workflow_run_id": "wf-1"}

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_core = FakeAgentCoreClient()
        workflow = FakeWorkflowAdapter()
        controller = SessionController(sessions_dir=tmpdir, agent_core_client=agent_core, workflow_adapter=workflow)
        result = controller.create_session(
            CreateSessionRequest(
                prompt="initial",
                repo_id="repo-1",
                allowed_actions=["read_file", "grep", "run_tests"],
            )
        )
        session_id = result["session"]["session_id"]
        persist_ambient_event(_browser_selection_event(session_id), sessions_dir=tmpdir)
        session = controller.session_store.get(session_id)
        plan_result = asyncio.run(controller._request_next_action_and_start_workflow(session, "fix selected button"))
        events = controller.event_store.get_events(session_id)

    assert plan_result["next_suggested_action"]["action_name"] == "read_file"
    assert agent_core.recommend_next_call["ambient_context"]["source_candidates"][0]["path"] == "src/components/SaveButton.tsx"
    assert agent_core.validate_action_call == {"action_name": "read_file", "params": {"path": "src/components/SaveButton.tsx"}}
    assert workflow.plan["source"] == "next_suggested_plan"
    assert len(workflow.plan["steps"]) == 1
    assert workflow.context["ambient_prompt_context"]
    assert any(event["event_type"] == "plan_requested" and event["data"].get("recommendation_source") == "recommend_next" for event in events)
    assert any(event["event_type"] == "plan_generated" and event["data"].get("source") == "next_suggested_plan" for event in events)


def test_session_controller_blocks_invalid_recommended_action_before_workflow():
    import asyncio

    from sessions.controller import CreateSessionRequest, SessionController

    class FakeAgentCoreClient:
        async def recommend_next(self, **kwargs):
            return {"ok": True, "next_action": {"action_name": "read_file", "params": {}}}

        async def validate_action(self, action_name, params):
            return {"valid": False, "errors": ["path is required"]}

    class FakeWorkflowAdapter:
        def __init__(self):
            self.started = False

        async def start_plan(self, session_id, plan, context):
            self.started = True
            return {"backend": "fake"}

    with tempfile.TemporaryDirectory() as tmpdir:
        workflow = FakeWorkflowAdapter()
        controller = SessionController(
            sessions_dir=tmpdir,
            agent_core_client=FakeAgentCoreClient(),
            workflow_adapter=workflow,
        )
        result = controller.create_session(
            CreateSessionRequest(prompt="initial", repo_id="repo-1", allowed_actions=["read_file"])
        )
        session = controller.session_store.get(result["session"]["session_id"])
        plan_result = asyncio.run(controller._request_next_action_and_start_workflow(session, "fix selected button"))

    assert "path is required" in plan_result["error"]
    assert workflow.started is False


def _browser_selection_event(session_id: str):
    from ambient.types import AmbientEvent, AmbientSource

    return AmbientEvent(
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
