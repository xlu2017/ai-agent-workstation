"""
CompositeActionAdapter interface — multi-step agentic action subflows.

Composite actions are multi-step internal loops:
  autonomous_code_edit
  repair_test_failure
  browser_debug_loop
  multi_file_refactor_loop
  investigate_and_patch

Atomic actions (grep, read_file, apply_patch, run_tests, summarize_diff, commit)
go directly through ExecutionRouter, NOT through composite adapters.
"""

from __future__ import annotations

import abc
from typing import Any


# Actions that are composite (multi-step agentic loops)
COMPOSITE_ACTIONS = frozenset({
    "autonomous_code_edit",
    "repair_test_failure",
    "browser_debug_loop",
    "multi_file_refactor_loop",
    "investigate_and_patch",
})

# Actions that are atomic (single-step execution)
ATOMIC_ACTIONS = frozenset({
    "classify_task",
    "retrieve_context",
    "search_memory",
    "grep",
    "read_file",
    "identify_relevant_tests",
    "apply_patch",
    "run_tests",
    "summarize_diff",
    "request_approval",
    "commit",
})


def is_composite_action(action_name: str) -> bool:
    """Check if an action is a composite (multi-step) action."""
    return action_name in COMPOSITE_ACTIONS


class CompositeActionAdapter(abc.ABC):
    """Abstract base for composite action execution."""

    @abc.abstractmethod
    async def execute_composite_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a composite (multi-step) action.

        Returns:
            {
                status: succeeded | failed | blocked | skipped,
                backend: langgraph | fallback_composite,
                output: {substeps: [], final_observation: {}},
                error: "",
                files_touched: [],
                duration_ms: int,
            }
        """
        ...
