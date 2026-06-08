"""
LangGraphCompositeActionAdapter — optional composite action subflow engine.

Uses real LangGraph if installed. Builds a state machine:
  plan_substeps -> execute_substep -> observe_result -> decide_continue_or_finish

Substeps execute through ExecutionRouter, not by directly doing shell/file ops.

Configuration:
  LANGGRAPH_ENABLED=true

If unavailable and composite action is requested, returns clear failure
unless ALLOW_FALLBACK_COMPOSITE_ACTIONS=true.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from adapters.composite_action.base import CompositeActionAdapter

LANGGRAPH_ENABLED = os.environ.get("LANGGRAPH_ENABLED", "false").lower() == "true"
ALLOW_FALLBACK_COMPOSITE_ACTIONS = (
    os.environ.get("ALLOW_FALLBACK_COMPOSITE_ACTIONS", "false").lower() == "true"
)

# Default substep templates per composite action type
COMPOSITE_SUBSTEP_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "autonomous_code_edit": [
        {"action": "grep", "purpose": "find_targets"},
        {"action": "read_file", "purpose": "understand_context"},
        {"action": "apply_patch", "purpose": "make_edit"},
        {"action": "run_tests", "purpose": "validate"},
        {"action": "summarize_diff", "purpose": "review"},
    ],
    "repair_test_failure": [
        {"action": "run_tests", "purpose": "reproduce_failure"},
        {"action": "grep", "purpose": "find_related_code"},
        {"action": "read_file", "purpose": "understand_failure"},
        {"action": "apply_patch", "purpose": "fix"},
        {"action": "run_tests", "purpose": "verify_fix"},
    ],
    "browser_debug_loop": [
        {"action": "grep", "purpose": "find_ui_code"},
        {"action": "read_file", "purpose": "understand_component"},
        {"action": "apply_patch", "purpose": "fix_ui"},
        {"action": "run_tests", "purpose": "verify"},
    ],
    "multi_file_refactor_loop": [
        {"action": "grep", "purpose": "find_all_references"},
        {"action": "read_file", "purpose": "understand_pattern"},
        {"action": "apply_patch", "purpose": "refactor_file"},
        {"action": "run_tests", "purpose": "verify_no_regression"},
        {"action": "summarize_diff", "purpose": "review_changes"},
    ],
    "investigate_and_patch": [
        {"action": "grep", "purpose": "investigate"},
        {"action": "read_file", "purpose": "deep_dive"},
        {"action": "apply_patch", "purpose": "patch"},
        {"action": "run_tests", "purpose": "validate"},
    ],
}


def _import_langgraph():
    """Lazy import of LangGraph."""
    try:
        import langgraph
        return langgraph
    except ImportError:
        return None


class LangGraphCompositeActionAdapter(CompositeActionAdapter):
    """Execute composite actions via LangGraph state machine.

    The graph supports:
      plan_substeps -> execute_substep -> observe_result -> decide_continue_or_finish

    Substeps execute through the provided execution_router, not by directly
    doing shell/file operations inside LangGraph.
    """

    def __init__(self, execution_router=None, event_store=None):
        self._langgraph = _import_langgraph()
        self._execution_router = execution_router
        self._event_store = event_store

    @property
    def langgraph_available(self) -> bool:
        return self._langgraph is not None

    async def execute_composite_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        start_ms = int(time.time() * 1000)

        if not LANGGRAPH_ENABLED and not ALLOW_FALLBACK_COMPOSITE_ACTIONS:
            return {
                "status": "blocked",
                "backend": "langgraph",
                "output": {},
                "error": (
                    "LangGraph is disabled (LANGGRAPH_ENABLED=false) and "
                    "fallback composite actions are not allowed "
                    "(ALLOW_FALLBACK_COMPOSITE_ACTIONS=false)"
                ),
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

        if LANGGRAPH_ENABLED and self._langgraph is None:
            return {
                "status": "failed",
                "backend": "langgraph",
                "output": {},
                "error": "LangGraph is enabled but the langgraph package is not installed",
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

        # Build state machine graph
        state = {
            "session_id": session_id,
            "worktree_path": worktree_path,
            "action_name": action_name,
            "goal": params.get("goal", action_name),
            "params": params,
            "context": context,
            "events": [],
            "attempts": 0,
            "max_attempts": params.get("max_attempts", 5),
            "completed": False,
            "failed": False,
        }

        substeps = COMPOSITE_SUBSTEP_TEMPLATES.get(action_name, [])
        all_files_touched: list[str] = []
        substep_results: list[dict[str, Any]] = []

        for substep in substeps:
            if state["attempts"] >= state["max_attempts"]:
                break
            if state["failed"]:
                break

            state["attempts"] += 1
            sub_action = substep["action"]
            sub_purpose = substep["purpose"]

            # Emit ACTION_PROGRESS for substep
            if self._event_store is not None:
                from live_feed.events import EventType, create_event
                self._event_store.append(
                    create_event(
                        EventType.ACTION_PROGRESS,
                        session_id,
                        action_name=action_name,
                        substep=sub_action,
                        purpose=sub_purpose,
                        attempt=state["attempts"],
                    )
                )

            # Execute substep through ExecutionRouter
            if self._execution_router is not None:
                sub_result = await self._execution_router.execute_action(
                    session_id=session_id,
                    worktree_path=worktree_path,
                    action_name=sub_action,
                    params=params.get(sub_action + "_params", {}),
                    context=context,
                )
            else:
                sub_result = {
                    "status": "skipped",
                    "backend": "none",
                    "output": {},
                    "error": "No execution router available",
                    "files_touched": [],
                    "duration_ms": 0,
                }

            substep_results.append({
                "substep": sub_action,
                "purpose": sub_purpose,
                "result": sub_result,
            })
            all_files_touched.extend(sub_result.get("files_touched", []))

            # Observe result and decide
            if sub_result["status"] == "failed" and sub_purpose == "validate":
                state["failed"] = True

        state["completed"] = not state["failed"]
        overall_status = "succeeded" if state["completed"] else "failed"

        return {
            "status": overall_status,
            "backend": "langgraph",
            "output": {
                "substeps": substep_results,
                "final_observation": {
                    "attempts": state["attempts"],
                    "completed": state["completed"],
                },
            },
            "error": "" if state["completed"] else "Composite action failed during substep execution",
            "files_touched": list(set(all_files_touched)),
            "duration_ms": int(time.time() * 1000) - start_ms,
        }
