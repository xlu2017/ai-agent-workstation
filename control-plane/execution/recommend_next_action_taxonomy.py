"""Recommend-next action category taxonomy scaffold.

Intent
------
All known platform-visible actions must be classified under exactly one of the
four recommend-next decision categories before later controller dispatch chooses
more granular behavior.

This module is scaffold-only. It is not wired into request handling, workflow
execution, or runtime validation. The lists below document the intended complete
category map for the currently known action names.

Boundary rule
-------------
The controller-level output remains one of:

* execute
* find_out_more
* ask_user
* stop

Granular names such as ``create_child_goal`` or ``grep`` may appear as metadata
or later dispatch targets, but they are not first-class controller decision
outputs. App-automation provider/app-specific names such as ``gmail.search`` or
``outlook.create_email`` must remain aliases or routing metadata; the root
taxonomy tracks only top-level actions such as ``email.search`` or
``email.create``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from execution.recommend_next_app_automation_provider_inventory import (
    TOP_LEVEL_APP_AUTOMATION_ACTION_DECISION_TYPE,
)
from execution.recommend_next_execution_service import RecommendNextDecisionType


@dataclass(frozen=True)
class ActionCategoryEntry:
    """A scaffold-only catalog entry for a known platform action name."""

    action_name: str
    decision_type: RecommendNextDecisionType
    rationale: str


# Execute actions mutate platform/session/worktree state, start a concrete
# executor operation, or intentionally perform a direct user-requested platform
# action. Session creation and routing are intentionally placed here.
EXECUTE_ACTIONS: tuple[ActionCategoryEntry, ...] = (
    ActionCategoryEntry("append_to_current", RecommendNextDecisionType.EXECUTE, "Route user input into the current session."),
    ActionCategoryEntry("modify_current_plan", RecommendNextDecisionType.EXECUTE, "Route user input as a change to current work."),
    ActionCategoryEntry("interrupt_current", RecommendNextDecisionType.EXECUTE, "Apply a platform control operation to active work."),
    ActionCategoryEntry("spawn_child_session", RecommendNextDecisionType.EXECUTE, "Create or route to a child session."),
    ActionCategoryEntry("spawn_new_session", RecommendNextDecisionType.EXECUTE, "Create or route to a new root session."),
    ActionCategoryEntry("queue", RecommendNextDecisionType.EXECUTE, "Persist an execution queue decision."),
    ActionCategoryEntry("continue_active", RecommendNextDecisionType.EXECUTE, "Continue or create executable work under the active session."),
    ActionCategoryEntry("create_child_goal", RecommendNextDecisionType.EXECUTE, "Create a child goal after the type-level decision."),
    ActionCategoryEntry("create_sibling_goal", RecommendNextDecisionType.EXECUTE, "Create a sibling goal after the type-level decision."),
    ActionCategoryEntry("classify_task", RecommendNextDecisionType.EXECUTE, "Run a platform classification step."),
    ActionCategoryEntry("identify_relevant_tests", RecommendNextDecisionType.EXECUTE, "Derive validation targets for an implementation task."),
    ActionCategoryEntry("apply_patch", RecommendNextDecisionType.EXECUTE, "Mutate files in the worktree."),
    ActionCategoryEntry("run_tests", RecommendNextDecisionType.EXECUTE, "Run validation command selected by platform policy."),
    ActionCategoryEntry("request_approval", RecommendNextDecisionType.EXECUTE, "Create an approval gate artifact."),
    ActionCategoryEntry("commit", RecommendNextDecisionType.EXECUTE, "Create a real git commit after platform validation."),
    ActionCategoryEntry("commit_checkpoint", RecommendNextDecisionType.EXECUTE, "Request a commit checkpoint; actual commit remains separately validated."),
    ActionCategoryEntry("autonomous_code_edit", RecommendNextDecisionType.EXECUTE, "Run a bounded composite coding action."),
    ActionCategoryEntry("repair_test_failure", RecommendNextDecisionType.EXECUTE, "Run a bounded composite repair action."),
    ActionCategoryEntry("browser_debug_loop", RecommendNextDecisionType.EXECUTE, "Run a bounded browser debugging composite action."),
    ActionCategoryEntry("multi_file_refactor_loop", RecommendNextDecisionType.EXECUTE, "Run a bounded multi-file refactor composite action."),
    ActionCategoryEntry("investigate_and_patch", RecommendNextDecisionType.EXECUTE, "Investigate and patch in a bounded executor step."),
    ActionCategoryEntry("open_terminal", RecommendNextDecisionType.EXECUTE, "Direct desktop action requested by the user."),
    ActionCategoryEntry("open_browser", RecommendNextDecisionType.EXECUTE, "Direct desktop action requested by the user."),
    ActionCategoryEntry("open_file_manager", RecommendNextDecisionType.EXECUTE, "Direct desktop action requested by the user."),
    ActionCategoryEntry("take_screenshot", RecommendNextDecisionType.EXECUTE, "Direct desktop action requested by the user."),
    ActionCategoryEntry("pause", RecommendNextDecisionType.EXECUTE, "Apply a platform pause control operation."),
    ActionCategoryEntry("resume", RecommendNextDecisionType.EXECUTE, "Apply a platform resume control operation."),
    ActionCategoryEntry("continue", RecommendNextDecisionType.EXECUTE, "Apply a platform continue control operation."),
    ActionCategoryEntry("cancel", RecommendNextDecisionType.EXECUTE, "Apply a platform cancellation control operation."),
    ActionCategoryEntry("new_session", RecommendNextDecisionType.EXECUTE, "Create or route to a new session."),
    ActionCategoryEntry("parallel", RecommendNextDecisionType.EXECUTE, "Create or route parallel work."),
)


# Find-out-more actions gather information without intentionally mutating the
# repo/session execution state. Later runtime validation may still reject them
# if path, command, or permission constraints fail.
FIND_OUT_MORE_ACTIONS: tuple[ActionCategoryEntry, ...] = (
    ActionCategoryEntry("retrieve_context", RecommendNextDecisionType.FIND_OUT_MORE, "Fetch context relevant to the current decision."),
    ActionCategoryEntry("search_memory", RecommendNextDecisionType.FIND_OUT_MORE, "Search stored memory before deciding on concrete work."),
    ActionCategoryEntry("grep", RecommendNextDecisionType.FIND_OUT_MORE, "Search repository text without mutation."),
    ActionCategoryEntry("read_file", RecommendNextDecisionType.FIND_OUT_MORE, "Read a file without mutation."),
    ActionCategoryEntry("list_files", RecommendNextDecisionType.FIND_OUT_MORE, "List files without mutation."),
    ActionCategoryEntry("summarize_diff", RecommendNextDecisionType.FIND_OUT_MORE, "Summarize current changes without mutating them."),
    ActionCategoryEntry("inspect_repo_metadata", RecommendNextDecisionType.FIND_OUT_MORE, "Inspect repository metadata before execution."),
    ActionCategoryEntry("search_recent_events", RecommendNextDecisionType.FIND_OUT_MORE, "Inspect recent session events."),
    ActionCategoryEntry("run_safe_status_command", RecommendNextDecisionType.FIND_OUT_MORE, "Run a low-risk status command after validation."),
)


# Ask-user actions do not start work. They produce a user-visible question or
# clarification request.
ASK_USER_ACTIONS: tuple[ActionCategoryEntry, ...] = (
    ActionCategoryEntry("ask_user", RecommendNextDecisionType.ASK_USER, "Ask the user for missing information."),
    ActionCategoryEntry("request_missing_information", RecommendNextDecisionType.ASK_USER, "Ask for data that tools cannot infer."),
    ActionCategoryEntry("clarify_goal", RecommendNextDecisionType.ASK_USER, "Clarify the user goal before execution."),
    ActionCategoryEntry("clarify_repo", RecommendNextDecisionType.ASK_USER, "Ask which repository/context the user intends."),
    ActionCategoryEntry("clarify_approval", RecommendNextDecisionType.ASK_USER, "Ask whether a gated action should proceed."),
)


# Stop actions deliberately do not start more work for the current input.
# Missing repo context is classified here by design.
STOP_ACTIONS: tuple[ActionCategoryEntry, ...] = (
    ActionCategoryEntry("stop", RecommendNextDecisionType.STOP, "Stop because the goal is complete or no action is needed."),
    ActionCategoryEntry("question_only", RecommendNextDecisionType.STOP, "Answer or record a question without creating work."),
    ActionCategoryEntry("blocked_needs_repo", RecommendNextDecisionType.STOP, "Missing repo context; do not start execution."),
    ActionCategoryEntry("missing_repo_context", RecommendNextDecisionType.STOP, "Missing repo context; do not start execution."),
    ActionCategoryEntry("blocked_needs_user", RecommendNextDecisionType.STOP, "Blocked until user provides required input."),
    ActionCategoryEntry("blocked_by_policy", RecommendNextDecisionType.STOP, "Blocked by platform policy."),
    ActionCategoryEntry("unsafe_to_continue", RecommendNextDecisionType.STOP, "Stop because continuing would be unsafe."),
    ActionCategoryEntry("goal_satisfied", RecommendNextDecisionType.STOP, "Stop because the user goal is satisfied."),
)


APP_AUTOMATION_TOP_LEVEL_ACTIONS: tuple[ActionCategoryEntry, ...] = tuple(
    ActionCategoryEntry(
        action_name=action_name,
        decision_type=decision_type,
        rationale="Provider-neutral app-automation action; provider/app-specific names are aliases only.",
    )
    for action_name, decision_type in sorted(TOP_LEVEL_APP_AUTOMATION_ACTION_DECISION_TYPE.items())
)


ALL_ACTION_CATEGORY_ENTRIES: tuple[ActionCategoryEntry, ...] = (
    *EXECUTE_ACTIONS,
    *FIND_OUT_MORE_ACTIONS,
    *ASK_USER_ACTIONS,
    *STOP_ACTIONS,
    *APP_AUTOMATION_TOP_LEVEL_ACTIONS,
)


ACTION_DECISION_TYPE_BY_NAME: Mapping[str, RecommendNextDecisionType] = {
    entry.action_name: entry.decision_type for entry in ALL_ACTION_CATEGORY_ENTRIES
}


# Scaffold invariant for future implementation:
# any recommend-next action name not present in ACTION_DECISION_TYPE_BY_NAME
# must fail closed until explicitly categorized here. Do not silently default
# unknown actions to execute. Provider/app-specific aliases must be normalized
# before this root-level lookup.
