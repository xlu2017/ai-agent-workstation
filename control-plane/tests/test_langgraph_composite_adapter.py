"""
Tests for CompositeActionAdapter, LangGraphCompositeActionAdapter, and CompositeActionRouter.

Covers:
  12. CompositeActionRouter selects LangGraph for composite actions when enabled
  13. CompositeActionRouter does not route atomic actions through LangGraph
  14. LangGraphCompositeActionAdapter returns clear failure when LangGraph unavailable
  19. Composite action emits ACTION_PROGRESS for substeps
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


class TestCompositeActionBase:
    def test_composite_actions_identified(self):
        from adapters.composite_action.base import is_composite_action
        assert is_composite_action("autonomous_code_edit")
        assert is_composite_action("repair_test_failure")
        assert is_composite_action("browser_debug_loop")
        assert is_composite_action("multi_file_refactor_loop")
        assert is_composite_action("investigate_and_patch")

    def test_atomic_actions_not_composite(self):
        from adapters.composite_action.base import is_composite_action
        assert not is_composite_action("grep")
        assert not is_composite_action("read_file")
        assert not is_composite_action("apply_patch")
        assert not is_composite_action("run_tests")
        assert not is_composite_action("commit")


class TestLangGraphCompositeActionAdapter:
    @pytest.mark.asyncio
    async def test_blocked_when_disabled_and_no_fallback(self):
        os.environ["LANGGRAPH_ENABLED"] = "false"
        os.environ["ALLOW_FALLBACK_COMPOSITE_ACTIONS"] = "false"
        # Need to re-import to pick up env
        from adapters.composite_action.langgraph_adapter import (
            LangGraphCompositeActionAdapter,
        )
        adapter = LangGraphCompositeActionAdapter()
        result = await adapter.execute_composite_action(
            "s1", "/tmp/wt", "autonomous_code_edit", {}, {},
        )
        assert result["status"] == "blocked"
        assert "LangGraph is disabled" in result["error"]

    @pytest.mark.asyncio
    async def test_runs_with_fallback_composite_and_mock_router(self):
        """When LangGraph package is not installed but fallback is allowed,
        the adapter should still execute composite actions through substep templates."""
        from adapters.composite_action import langgraph_adapter
        # Override module-level constants to simulate: LangGraph disabled, fallback allowed
        orig_lg = langgraph_adapter.LANGGRAPH_ENABLED
        orig_fb = langgraph_adapter.ALLOW_FALLBACK_COMPOSITE_ACTIONS
        langgraph_adapter.LANGGRAPH_ENABLED = False
        langgraph_adapter.ALLOW_FALLBACK_COMPOSITE_ACTIONS = True

        try:
            mock_router = AsyncMock()
            mock_router.execute_action = AsyncMock(return_value={
                "status": "succeeded",
                "backend": "fallback",
                "output": {"result": "ok"},
                "error": "",
                "files_touched": ["file.py"],
                "duration_ms": 10,
            })

            tmpdir = tempfile.mkdtemp()
            from live_feed.events import EventStore
            event_store = EventStore(tmpdir)

            adapter = langgraph_adapter.LangGraphCompositeActionAdapter(
                execution_router=mock_router,
                event_store=event_store,
            )
            result = await adapter.execute_composite_action(
                "s1", "/tmp/wt", "autonomous_code_edit", {}, {},
            )
            # When LangGraph is disabled but fallback allowed, adapter runs substep templates
            assert result["status"] == "succeeded"
            assert result["backend"] == "langgraph"
            assert len(result["output"]["substeps"]) > 0
            assert mock_router.execute_action.call_count > 0

            # Verify ACTION_PROGRESS events emitted
            events = event_store.get_events("s1")
            progress_events = [
                e for e in events if e["event_type"] == "action_progress"
            ]
            assert len(progress_events) > 0
        finally:
            langgraph_adapter.LANGGRAPH_ENABLED = orig_lg
            langgraph_adapter.ALLOW_FALLBACK_COMPOSITE_ACTIONS = orig_fb


class TestCompositeActionRouter:
    @pytest.mark.asyncio
    async def test_rejects_atomic_action(self):
        from adapters.composite_action.router import CompositeActionRouter
        router = CompositeActionRouter()
        result = await router.execute_composite_action(
            "s1", "/tmp/wt", "grep", {}, {},
        )
        assert result["status"] == "failed"
        assert "not a composite action" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_when_langgraph_disabled(self):
        from adapters.composite_action.router import CompositeActionRouter
        router = CompositeActionRouter(
            langgraph_enabled=False,
            allow_fallback_composite=False,
        )
        result = await router.execute_composite_action(
            "s1", "/tmp/wt", "autonomous_code_edit", {}, {},
        )
        assert result["status"] == "blocked"
        assert "LangGraph" in result["error"]

    @pytest.mark.asyncio
    async def test_fallback_composite_via_execution_router(self):
        mock_exec = AsyncMock()
        mock_exec.execute_action = AsyncMock(return_value={
            "status": "succeeded",
            "backend": "fallback",
            "output": {},
            "error": "",
            "files_touched": [],
            "duration_ms": 5,
        })
        from adapters.composite_action.router import CompositeActionRouter
        router = CompositeActionRouter(
            execution_router=mock_exec,
            langgraph_enabled=False,
            allow_fallback_composite=True,
        )
        result = await router.execute_composite_action(
            "s1", "/tmp/wt", "repair_test_failure", {}, {},
        )
        assert result["status"] == "succeeded"
        assert "fallback_composite" in result["backend"]
