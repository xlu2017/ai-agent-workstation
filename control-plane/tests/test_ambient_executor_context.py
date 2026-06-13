import sys
from pathlib import Path

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


@pytest.mark.asyncio
async def test_plan_executor_forwards_ambient_prompt_context_as_plan_context(tmp_path):
    from adapters.composite_action.router import CompositeActionRouter
    from execution.results import ExecutionResult
    from execution.runtime_validator import RuntimeValidator
    from live_feed.events import EventStore
    from sessions.models import Session, SessionStore
    from workflows.execute_agent_plan import PlanExecutor

    worktree = tmp_path / "repos" / "wt-1"
    worktree.mkdir(parents=True)
    session_store = SessionStore(tmp_path / "sessions")
    event_store = EventStore(tmp_path / "sessions")
    session_store.save(Session(session_id="s1", worktree_id="wt-1", allowed_actions=["grep"]))

    class CapturingExecutionRouter:
        def __init__(self):
            self.context = None

        async def execute_action(self, session_id, worktree_path, action_name, params, context):
            self.context = context
            return ExecutionResult(status="succeeded", backend="fake", summary="ok")

    execution_router = CapturingExecutionRouter()
    composite_router = CompositeActionRouter(
        execution_router=execution_router,
        event_store=event_store,
        langgraph_enabled=False,
        allow_fallback_composite=False,
    )
    validator = RuntimeValidator(session_store, worktree_base=str(tmp_path / "repos"))
    executor = PlanExecutor(
        session_store=session_store,
        event_store=event_store,
        execution_router=execution_router,
        composite_router=composite_router,
        runtime_validator=validator,
        worktree_base=str(tmp_path / "repos"),
    )
    plan = {"mode": "finite", "steps": [{"action_name": "grep", "params": {"pattern": "SaveButton"}}]}

    result = await executor.execute(
        "s1",
        plan,
        {
            "worktree_id": "wt-1",
            "ambient_prompt_context": "Ambient context evidence:\n- Ranked source candidates:\n  - src/components/SaveButton.tsx:12",
        },
    )

    assert result["completed"] is True
    assert execution_router.context["ambient_prompt_context"].startswith("Ambient context evidence")
    assert execution_router.context["plan_context"].startswith("Ambient context evidence")
