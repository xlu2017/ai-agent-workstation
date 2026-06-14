"""Session-graph to execution activation bridge scaffold.

Intent
------
Graph chat creates ``SessionKind.WORK`` nodes. Those nodes are not executable by
being present in the graph; they must be translated into the same activation
contract used by classic session prompts.

This module provides that translation and records activation intent on graph work
sessions without claiming that execution started. The scaffold now records the
next execution boundary explicitly:

    ready work session
    -> workflow adapter start boundary
    -> first read/search action
    -> next LLM call after the read/search outcome

The future implementation should inject ``ExecutionActivationService`` with the
extracted workflow-start callback and set ``auto_started`` only after that
callback succeeds.
"""

from __future__ import annotations

from typing import Any

from api.models.session_graph import SessionKind, SessionRecord, SessionStatus
from execution.activation import (
    ExecutionActivationRequest,
    ExecutionActivationResult,
    ExecutionActivationSource,
    ExecutionActivationStatus,
)


def work_facet(session: SessionRecord) -> dict[str, Any]:
    facet = session.facets.get("work", {})
    return facet if isinstance(facet, dict) else {}


def should_activate_graph_work_session(session: SessionRecord) -> bool:
    """Return true when a graph work session should enter activation flow.

    This means the work is ready and pending. It does not mean the platform is
    allowed to execute it; runtime validation still happens later.
    """

    facet = work_facet(session)
    return (
        session.kind == SessionKind.WORK
        and session.status == SessionStatus.ACTIVE
        and facet.get("execution_state") == "ready_for_execution"
        and facet.get("requires_execution_start") is True
        and facet.get("auto_started") is not True
    )


def build_graph_work_activation_request(
    *,
    work_session: SessionRecord,
    parent_session: SessionRecord | None,
    source: ExecutionActivationSource = ExecutionActivationSource.SESSION_GRAPH_CHAT,
) -> ExecutionActivationRequest:
    """Translate graph work-session state into the shared activation request."""

    facet = work_facet(work_session)
    parent_metadata = parent_session.metadata if parent_session is not None else {}
    prompt = str(facet.get("prompt") or work_session.summary or work_session.title)
    repo_context_id = str(
        work_session.metadata.get("repo_session_id")
        or parent_metadata.get("repo_session_id")
        or ""
    )
    return ExecutionActivationRequest(
        session_id=work_session.id,
        parent_session_id=work_session.parent_id or (parent_session.id if parent_session else ""),
        root_session_id=work_session.root_id or (parent_session.root_id if parent_session else "") or "",
        prompt=prompt,
        source=source,
        mode_preference=str(facet.get("mode") or "finite"),
        repo_context_id=repo_context_id,
        allowed_actions=[str(action) for action in facet.get("allowed_actions", []) if action],
        metadata={
            "graph_session_kind": work_session.kind.value,
            "source_session_id": facet.get("source_session_id") or work_session.parent_id or "",
            "created_from": work_session.metadata.get("created_from") or "",
        },
    )


def _initial_context_action(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Build the first low-risk repo context action for a ready work session.

    This is an action proposal, not an executed action. The workflow adapter must
    still validate and run it before the next LLM call is allowed.
    """

    return {
        "decision": "find_out_more",
        "task_name": "search_code",
        "params": {
            "query": request.prompt,
            "scope": request.repo_context_id or request.repo_id or request.worktree_id or "repository",
        },
        "stakes": "read_only",
        "risk": "low",
        "requires_platform_validation": True,
        "reason": "Read repository context before answering or modifying files.",
        "expected_result": "Relevant repository references, files, or code locations for the work prompt.",
        "success_criteria": [
            "Repository context was searched or inspected.",
            "The outcome is recorded before the next LLM decision.",
        ],
    }


def build_graph_work_execution_plan(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Return the scaffolded execution plan for graph-created work.

    The plan intentionally contains exactly one first action. After that action's
    outcome is recorded, the platform must call recommend-next again rather than
    executing a second top-level action from this scaffold.
    """

    first_action = _initial_context_action(request)
    return {
        "mode": request.mode_preference or "finite",
        "source": request.source.value,
        "work_session_id": request.session_id,
        "repo_context_id": request.repo_context_id,
        "workflow_start": {
            "status": "scaffolded_not_started",
            "adapter_required": True,
            "auto_started": False,
        },
        "steps": [first_action],
        "after_step": {
            "record_outcome": True,
            "next_required_phase": "recommend_next_after_context_outcome",
            "requires_llm_after_outcome": True,
            "max_top_level_actions_before_next_llm": 1,
        },
    }


def record_activation_result_on_work_session(
    work_session: SessionRecord,
    result: ExecutionActivationResult,
) -> SessionRecord:
    """Record activation result on a work session without fabricating success."""

    facet = dict(work_facet(work_session))
    activation_record = result.to_response_dict()
    facet["activation"] = activation_record
    facet["auto_started"] = result.auto_started
    if result.status == ExecutionActivationStatus.STARTED:
        facet["execution_state"] = "started"
        facet["requires_execution_start"] = False
    elif result.status == ExecutionActivationStatus.BLOCKED_NEEDS_REPO:
        facet["execution_state"] = "blocked_needs_repo"
        facet["requires_execution_start"] = False
    else:
        facet["execution_state"] = facet.get("execution_state") or "ready_for_execution"

    work_session.facets = {**work_session.facets, "work": facet}
    work_session.state = {
        **work_session.state,
        "execution_activation": activation_record,
        "auto_started": result.auto_started,
    }
    return work_session


def scaffold_activation_result(request: ExecutionActivationRequest) -> ExecutionActivationResult:
    """Build a deterministic non-executing activation result for graph chat.

    This keeps graph chat wired to the activation boundary before the real
    workflow-start callback is extracted. When repo context exists, the response
    includes the first read/search action and the requirement to make the next LLM
    call only after that action outcome is recorded.
    """

    if not request.has_repo_context:
        return ExecutionActivationResult(
            status=ExecutionActivationStatus.BLOCKED_NEEDS_REPO,
            message="Repository context is required before execution can start.",
            metadata={"source": request.source.value},
        )

    plan = build_graph_work_execution_plan(request)
    return ExecutionActivationResult(
        status=ExecutionActivationStatus.READY_NOT_STARTED,
        message="Execution activation scaffold recorded; workflow start is not wired from graph chat yet.",
        plan=plan,
        workflow={
            "status": "not_started",
            "adapter": "workflow_adapter",
            "reason": "Workflow adapter start callback is not wired from graph chat yet.",
            "first_action_status": "proposed_not_executed",
            "next_llm_call": "after_first_action_outcome",
        },
        metadata={
            "source": request.source.value,
            "requires_shared_activation_service": True,
            "workflow_adapter_start_scaffolded": True,
            "initial_context_action": plan["steps"][0],
            "next_llm_after_outcome": plan["after_step"],
        },
    )
