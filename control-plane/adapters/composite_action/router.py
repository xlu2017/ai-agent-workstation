"""
CompositeActionRouter — routes composite actions to the appropriate adapter.

Rules:
  If action is composite AND LANGGRAPH_ENABLED=true:
    use LangGraphCompositeActionAdapter

  If LANGGRAPH_ENABLED=false or unavailable:
    return clear failure unless ALLOW_FALLBACK_COMPOSITE_ACTIONS=true

  If fallback composite is allowed:
    route to ExecutionRouter as one high-level instruction

Atomic actions must NOT be routed through this router.
"""

from __future__ import annotations

import os
import time
from typing import Any

from adapters.composite_action.base import CompositeActionAdapter, is_composite_action
from adapters.composite_action.langgraph_adapter import (
    ALLOW_FALLBACK_COMPOSITE_ACTIONS,
    LANGGRAPH_ENABLED,
    LangGraphCompositeActionAdapter,
)


class CompositeActionRouter:
    """Routes composite actions to the appropriate execution path."""

    def __init__(
        self,
        execution_router=None,
        event_store=None,
        langgraph_enabled: bool | None = None,
        allow_fallback_composite: bool | None = None,
    ):
        self._execution_router = execution_router
        self._event_store = event_store
        self._langgraph_enabled = (
            langgraph_enabled if langgraph_enabled is not None else LANGGRAPH_ENABLED
        )
        self._allow_fallback = (
            allow_fallback_composite
            if allow_fallback_composite is not None
            else ALLOW_FALLBACK_COMPOSITE_ACTIONS
        )
        self._langgraph_adapter: LangGraphCompositeActionAdapter | None = None

    def _get_langgraph_adapter(self) -> LangGraphCompositeActionAdapter:
        if self._langgraph_adapter is None:
            self._langgraph_adapter = LangGraphCompositeActionAdapter(
                execution_router=self._execution_router,
                event_store=self._event_store,
            )
        return self._langgraph_adapter

    async def execute_composite_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not is_composite_action(action_name):
            return {
                "status": "failed",
                "backend": "composite_router",
                "output": {},
                "error": f"{action_name} is not a composite action; use ExecutionRouter",
                "files_touched": [],
                "duration_ms": 0,
            }

        if self._langgraph_enabled:
            adapter = self._get_langgraph_adapter()
            return await adapter.execute_composite_action(
                session_id, worktree_path, action_name, params, context
            )

        if self._allow_fallback and self._execution_router is not None:
            # Route to agentic/deterministic executor as a single high-level instruction
            start_ms = int(time.time() * 1000)
            result = await self._execution_router.execute_action(
                session_id=session_id,
                worktree_path=worktree_path,
                action_name=action_name,
                params=params,
                context=context,
            )
            result["duration_ms"] = int(time.time() * 1000) - start_ms
            result["backend"] = f"fallback_composite_via_{result.get('backend', 'unknown')}"
            return result

        return {
            "status": "blocked",
            "backend": "composite_router",
            "output": {},
            "error": (
                f"Composite action {action_name} requires LangGraph "
                "(LANGGRAPH_ENABLED=true) or fallback composite mode "
                "(ALLOW_FALLBACK_COMPOSITE_ACTIONS=true)"
            ),
            "files_touched": [],
            "duration_ms": 0,
        }
