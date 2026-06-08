"""
Tests for WorkflowAdapter implementations.

Covers:
  - InProcessWorkflowAdapter start/pause/resume/cancel/status
  - HatchetWorkflowAdapter raises when SDK unavailable
"""

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


class TestInProcessWorkflowAdapter:
    def setup_method(self):
        from adapters.workflow.inprocess_adapter import InProcessWorkflowAdapter
        self.adapter = InProcessWorkflowAdapter()

    @pytest.mark.asyncio
    async def test_start_plan_returns_started(self):
        result = await self.adapter.start_plan(
            "s1", {"steps": []}, {"repo_id": "r1"}
        )
        assert result["started"] is True
        assert result["backend"] == "inprocess"
        assert result["session_id"] == "s1"
        assert "workflow_run_id" in result

    @pytest.mark.asyncio
    async def test_pause_returns_accepted(self):
        result = await self.adapter.pause("s1")
        assert result["accepted"] is True
        assert result["mechanism"] == "session_state_control_intent"

    @pytest.mark.asyncio
    async def test_resume_clears_control_intent(self):
        await self.adapter.pause("s1")
        assert self.adapter.get_control_intent("s1") == "pause"
        await self.adapter.resume("s1")
        assert self.adapter.get_control_intent("s1") == ""

    @pytest.mark.asyncio
    async def test_cancel_sets_intent_and_cancels_task(self):
        result = await self.adapter.cancel("s1")
        assert result["accepted"] is True
        assert self.adapter.get_control_intent("s1") == "cancel"

    @pytest.mark.asyncio
    async def test_status_returns_intent(self):
        status = await self.adapter.status("s1")
        assert status["backend"] == "inprocess"
        assert status["control_intent"] == "running"

    @pytest.mark.asyncio
    async def test_workflow_fn_is_called(self):
        called = {}

        async def mock_workflow(session_id, plan, context):
            called["session_id"] = session_id
            called["plan"] = plan

        self.adapter.set_workflow_fn(mock_workflow)
        await self.adapter.start_plan("s1", {"steps": [1]}, {})
        await asyncio.sleep(0.1)
        assert called.get("session_id") == "s1"
        assert called.get("plan") == {"steps": [1]}


class TestHatchetWorkflowAdapterUnavailable:
    def test_raises_when_sdk_not_installed(self):
        from adapters.workflow.hatchet_adapter import HatchetWorkflowAdapter
        with pytest.raises(RuntimeError, match="Hatchet SDK is not installed"):
            HatchetWorkflowAdapter()
