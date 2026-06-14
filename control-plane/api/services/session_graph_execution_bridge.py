"""Session-graph to execution bridge.

Graph chat creates ``SessionKind.WORK`` nodes. Those nodes become executable only
through the shared execution activation boundary:

    ready work session
    -> request agent-core recommend-next
    -> validate the action contract
    -> validate platform/runtime permissions
    -> start the workflow adapter
    -> emit truthful events

The session graph is the canonical user-facing session model. The deprecated
``sessions.models.Session`` record is created only as an internal compatibility
record for the current runtime validator and workflow executor.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from adapters.composite_action.router import CompositeActionRouter
from adapters.execution.router import ExecutionRouter
from adapters.workflow.hatchet_adapter import HatchetWorkflowAdapter
from adapters.workflow.inprocess_adapter import InProcessWorkflowAdapter
from agent_core_client.client import AgentCoreClient
from api.models.session_graph import SessionKind, SessionRecord, SessionStatus
from execution.activation import (
    ExecutionActivationRequest,
    ExecutionActivationResult,
    ExecutionActivationSource,
    ExecutionActivationStatus,
)
from execution.ambient_prompt_context import (
    ambient_packet_to_agent_core_context,
    ambient_packet_to_prompt_block,
    load_ambient_context_packet,
)
from execution.next_suggested_plan import NextSuggestedPlanError, NextSuggestedStop, next_suggestion_to_plan
from execution.runtime_validator import RuntimeValidator
from live_feed.events import EventStore, EventType, create_event
from sessions.models import Session, SessionStatus as RuntimeSessionStatus, SessionStore, SessionType
from workflows.execute_agent_plan import PlanExecutor


DEFAULT_GRAPH_WORK_ALLOWED_ACTIONS = [
    "retrieve_context",
    "search_memory",
    "grep",
    "search_code",
    "read_file",
    "list_files",
    "git_status",
    "git_diff",
    "inspect_diff",
    "summarize_diff",
    "apply_patch",
    "write_file",
    "run_tests",
    "run_lint",
    "run_typecheck",
    "request_approval",
    "autonomous_code_edit",
    "investigate_and_patch",
    "repair_test_failure",
]


def work_facet(session: SessionRecord) -> dict[str, Any]:
    facet = session.facets.get("work", {})
    return facet if isinstance(facet, dict) else {}


def should_mark_graph_work_execution_ready(session: SessionRecord) -> bool:
    """Return true when a graph work session should enter readiness flow.

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


def should_activate_graph_work_session(session: SessionRecord) -> bool:
    """Backward-compatible alias for older callers."""

    return should_mark_graph_work_execution_ready(session)


def _string_metadata(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_graph_work_execution_readiness_request(
    *,
    work_session: SessionRecord,
    parent_session: SessionRecord | None,
    source: ExecutionActivationSource = ExecutionActivationSource.SESSION_GRAPH_CHAT,
) -> ExecutionActivationRequest:
    """Translate graph work-session state into the shared readiness request."""

    facet = work_facet(work_session)
    parent_metadata = parent_session.metadata if parent_session is not None else {}
    prompt = str(facet.get("prompt") or work_session.summary or work_session.title)
    repo_context_id = _string_metadata(
        work_session.metadata.get("repo_session_id"),
        parent_metadata.get("repo_session_id"),
    )
    repo_id = _string_metadata(
        work_session.metadata.get("repo_id"),
        parent_metadata.get("repo_id"),
        repo_context_id,
    )
    worktree_id = _string_metadata(
        work_session.metadata.get("worktree_id"),
        parent_metadata.get("worktree_id"),
        work_session.metadata.get("repo_path"),
        parent_metadata.get("repo_path"),
    )
    allowed_actions_raw = facet.get("allowed_actions") or work_session.metadata.get("allowed_actions") or parent_metadata.get("allowed_actions") or DEFAULT_GRAPH_WORK_ALLOWED_ACTIONS
    allowed_actions = [str(action) for action in allowed_actions_raw if action]
    return ExecutionActivationRequest(
        session_id=work_session.id,
        parent_session_id=work_session.parent_id or (parent_session.id if parent_session else ""),
        root_session_id=work_session.root_id or (parent_session.root_id if parent_session else "") or "",
        prompt=prompt,
        source=source,
        mode_preference=str(facet.get("mode") or "finite"),
        repo_id=repo_id,
        repo_context_id=repo_context_id,
        worktree_id=worktree_id,
        allowed_actions=allowed_actions,
        metadata={
            "graph_session_kind": work_session.kind.value,
            "source_session_id": facet.get("source_session_id") or work_session.parent_id or "",
            "created_from": work_session.metadata.get("created_from") or "",
        },
    )


def build_graph_work_activation_request(
    *,
    work_session: SessionRecord,
    parent_session: SessionRecord | None,
    source: ExecutionActivationSource = ExecutionActivationSource.SESSION_GRAPH_CHAT,
) -> ExecutionActivationRequest:
    """Backward-compatible alias for older callers."""

    return build_graph_work_execution_readiness_request(
        work_session=work_session,
        parent_session=parent_session,
        source=source,
    )


def _initial_context_action(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Build the first low-risk repo context action for a ready work session.

    This is an action proposal, not an executed action. The executor must still
    validate and run it before the next LLM call is allowed.
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


def build_graph_work_initial_execution_scaffold(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Return the scaffolded first-action contract for graph-created work.

    This function remains for tests and for explicit non-starting readiness
    inspection. The default graph chat path now uses ``start_graph_workflow`` via
    ``ExecutionActivationService``.
    """

    first_action = _initial_context_action(request)
    return {
        "mode": request.mode_preference or "finite",
        "source": request.source.value,
        "work_session_id": request.session_id,
        "repo_context_id": request.repo_context_id,
        "executor_start": {
            "status": "pending_adapter",
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


def build_graph_work_execution_plan(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Backward-compatible alias for older callers."""

    return build_graph_work_initial_execution_scaffold(request)


def execution_readiness_response(result: ExecutionActivationResult) -> dict[str, Any]:
    """Return the public graph-chat readiness payload without activation wording."""

    payload = result.to_response_dict()
    if "activation_id" in payload:
        payload["execution_readiness_id"] = payload.pop("activation_id")
    if "plan" in payload:
        payload["initial_execution_scaffold"] = payload.pop("plan")
    if "workflow" in payload:
        payload["executor"] = payload.pop("workflow")
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        if "requires_shared_activation_service" in metadata:
            metadata["requires_shared_execution_readiness_service"] = metadata.pop("requires_shared_activation_service")
        if "workflow_adapter_start_scaffolded" in metadata:
            metadata["executor_start_scaffolded"] = metadata.pop("workflow_adapter_start_scaffolded")
    return payload


def record_execution_readiness_on_work_session(
    work_session: SessionRecord,
    result: ExecutionActivationResult,
) -> SessionRecord:
    """Record execution readiness on a work session without fabricating success."""

    facet = dict(work_facet(work_session))
    readiness_record = execution_readiness_response(result)
    facet["execution_readiness"] = readiness_record
    facet["auto_started"] = result.auto_started
    if result.status == ExecutionActivationStatus.STARTED:
        facet["execution_state"] = "started"
        facet["requires_execution_start"] = False
        work_session.status = SessionStatus.ACTIVE
    elif result.status == ExecutionActivationStatus.BLOCKED_NEEDS_REPO:
        facet["execution_state"] = "blocked_needs_repo"
        facet["requires_execution_start"] = False
        work_session.status = SessionStatus.BLOCKED
    elif result.status == ExecutionActivationStatus.FAILED:
        facet["execution_state"] = "failed"
        facet["requires_execution_start"] = False
        work_session.status = SessionStatus.BLOCKED
    elif result.status == ExecutionActivationStatus.NOT_CONFIGURED:
        facet["execution_state"] = "not_configured"
        facet["requires_execution_start"] = False
        work_session.status = SessionStatus.BLOCKED
    else:
        facet["execution_state"] = facet.get("execution_state") or "ready_for_execution"

    work_session.facets = {**work_session.facets, "work": facet}
    work_session.state = {
        **work_session.state,
        "execution_readiness": readiness_record,
        "execution_state": facet.get("execution_state"),
        "auto_started": result.auto_started,
    }
    return work_session


def record_activation_result_on_work_session(
    work_session: SessionRecord,
    result: ExecutionActivationResult,
) -> SessionRecord:
    """Backward-compatible alias for older callers."""

    return record_execution_readiness_on_work_session(work_session, result)


def scaffold_execution_readiness_result(request: ExecutionActivationRequest) -> ExecutionActivationResult:
    """Build a deterministic non-executing readiness result for graph chat.

    This keeps a non-starting inspection path available. Production graph chat
    should use ``ExecutionActivationService(start_workflow=start_graph_workflow)``.
    """

    if not request.has_repo_context:
        return ExecutionActivationResult(
            status=ExecutionActivationStatus.BLOCKED_NEEDS_REPO,
            message="Repository context is required before execution can start.",
            metadata={"source": request.source.value},
        )

    scaffold = build_graph_work_initial_execution_scaffold(request)
    return ExecutionActivationResult(
        status=ExecutionActivationStatus.READY_NOT_STARTED,
        message="Execution readiness recorded; executor start was not requested.",
        plan=scaffold,
        workflow={
            "status": "not_started",
            "adapter": "workflow_adapter",
            "reason": "Executor start was not requested by this inspection path.",
            "first_action_status": "proposed_not_executed",
            "next_llm_call": "after_first_action_outcome",
        },
        metadata={
            "source": request.source.value,
            "requires_shared_activation_service": True,
            "workflow_adapter_start_scaffolded": True,
            "initial_context_action": scaffold["steps"][0],
            "next_llm_after_outcome": scaffold["after_step"],
        },
    )


def scaffold_activation_result(request: ExecutionActivationRequest) -> ExecutionActivationResult:
    """Backward-compatible alias for older callers."""

    return scaffold_execution_readiness_result(request)


def _sessions_dir() -> Path:
    return Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


def _worktree_base() -> Path:
    return Path(os.environ.get("WORKTREE_BASE", os.environ.get("REPOS_DIR", "/opt/workstation/repos")))


def _allow_deterministic_executor() -> bool:
    return os.environ.get("ALLOW_DETERMINISTIC_EXECUTOR", "true").lower() in {"1", "true", "yes"}


def _agentic_executor_enabled() -> bool:
    return os.environ.get("AGENTIC_EXECUTOR_ENABLED", "false").lower() in {"1", "true", "yes"}


def _workflow_backend() -> str:
    return os.environ.get("WORKFLOW_BACKEND", "inprocess").strip().lower() or "inprocess"


def _ensure_runtime_session(request: ExecutionActivationRequest, session_store: SessionStore) -> Session:
    session = session_store.get(request.session_id) or Session(session_id=request.session_id)
    session.session_type = SessionType.CHILD if request.parent_session_id else SessionType.ROOT
    session.status = RuntimeSessionStatus.CREATED
    session.repo_id = request.repo_id or request.repo_context_id
    session.worktree_id = request.worktree_id
    session.parent_session_id = request.parent_session_id
    session.root_session_id = request.root_session_id or request.session_id
    session.prompt = request.prompt
    session.allowed_actions = request.allowed_actions or DEFAULT_GRAPH_WORK_ALLOWED_ACTIONS
    return session_store.save(session)


def _build_workflow_adapter(
    *,
    session_store: SessionStore,
    event_store: EventStore,
    agent_core_client: AgentCoreClient,
    worktree_base: Path,
):
    backend = _workflow_backend()
    if backend == "hatchet":
        return HatchetWorkflowAdapter()
    if backend != "inprocess":
        raise RuntimeError(f"Unsupported WORKFLOW_BACKEND for graph execution: {backend}")

    execution_router = ExecutionRouter(
        agentic_enabled=_agentic_executor_enabled(),
        allow_deterministic=_allow_deterministic_executor(),
    )
    composite_router = CompositeActionRouter(execution_router=execution_router, event_store=event_store)
    runtime_validator = RuntimeValidator(session_store, worktree_base=worktree_base)
    executor = PlanExecutor(
        session_store=session_store,
        event_store=event_store,
        execution_router=execution_router,
        composite_router=composite_router,
        runtime_validator=runtime_validator,
        agent_core_client=agent_core_client,
        worktree_base=str(worktree_base),
    )
    adapter = InProcessWorkflowAdapter()
    adapter.set_workflow_fn(executor.execute)
    return adapter


def _validate_graph_one_step_plan(request: ExecutionActivationRequest, plan: dict[str, Any]) -> None:
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        raise NextSuggestedPlanError("recommend-next must produce exactly one graph execution action")
    step = steps[0]
    if not isinstance(step, dict):
        raise NextSuggestedPlanError("recommend-next graph execution action must be an object")
    action_name = str(step.get("action_name") or "").strip()
    if not action_name:
        raise NextSuggestedPlanError("recommend-next graph execution action is missing action_name")
    allowed_actions = request.allowed_actions or DEFAULT_GRAPH_WORK_ALLOWED_ACTIONS
    if allowed_actions and action_name not in allowed_actions:
        raise NextSuggestedPlanError(f"Action {action_name} is not in graph work allowed_actions")


async def start_graph_workflow(request: ExecutionActivationRequest) -> dict[str, Any]:
    """Start actual execution for a graph work session.

    A successful return means the workflow adapter accepted the one-action plan.
    Individual actions may still be blocked later by runtime validation.
    """

    if not request.worktree_id:
        raise RuntimeError(
            "Graph work execution requires an executable worktree_id or local repository path. "
            "A repository context session alone is not enough to run code."
        )

    sessions_dir = _sessions_dir()
    worktree_base = _worktree_base()
    session_store = SessionStore(sessions_dir)
    event_store = EventStore(sessions_dir)
    runtime_session = _ensure_runtime_session(request, session_store)
    agent_core_client = AgentCoreClient()

    ambient_packet = load_ambient_context_packet(request.session_id, goal=request.prompt, sessions_dir=sessions_dir)
    ambient_context = ambient_packet_to_agent_core_context(ambient_packet)
    ambient_prompt_block = ambient_packet_to_prompt_block(ambient_packet)
    allowed_actions = request.allowed_actions or DEFAULT_GRAPH_WORK_ALLOWED_ACTIONS

    session_store.update_status(request.session_id, RuntimeSessionStatus.PLANNING)
    event_store.append(
        create_event(
            EventType.PLAN_REQUESTED,
            request.session_id,
            prompt=request.prompt,
            mode_preference=request.mode_preference,
            recommendation_source="graph_recommend_next",
            source=request.source.value,
            parent_session_id=request.parent_session_id,
            root_session_id=request.root_session_id,
            repo_id=runtime_session.repo_id,
            worktree_id=runtime_session.worktree_id,
            visible_actions=allowed_actions,
            ambient_context_attached=bool(ambient_context),
            source_candidate_count=len(ambient_context.get("source_candidates", [])),
            evidence_event_ids=ambient_context.get("evidence_event_ids", []),
            ambient_prompt_context=ambient_prompt_block[:4000],
        )
    )

    try:
        recommendation = await agent_core_client.recommend_next(
            task_type="implementation",
            current_action=request.prompt,
            completed_actions=[],
            session_id=request.session_id,
            repo_id=runtime_session.repo_id,
            ambient_context=ambient_context,
            visible_actions=allowed_actions,
        )
    except Exception as exc:
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=str(exc), source="graph_recommend_next"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise RuntimeError(f"graph recommend-next request failed: {exc}") from exc

    if recommendation.get("ok") is False:
        error_msg = str(recommendation.get("error") or "graph recommend-next failed")
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=error_msg, source="graph_recommend_next_response"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise RuntimeError(error_msg)

    try:
        plan = next_suggestion_to_plan(prompt=request.prompt, recommendation=recommendation, mode_preference=request.mode_preference)
        _validate_graph_one_step_plan(request, plan)
    except NextSuggestedStop as exc:
        event_store.append(create_event(EventType.PLAN_COMPLETED, request.session_id, source="graph_recommend_next_stop", status="stopped", reason=exc.reason, recommendation=recommendation))
        session_store.update_status(request.session_id, RuntimeSessionStatus.COMPLETED)
        raise RuntimeError(f"graph recommend-next stopped before execution: {exc.reason}") from exc
    except NextSuggestedPlanError as exc:
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=str(exc), source="graph_next_suggested_plan_adapter"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise

    step = plan["steps"][0]
    action_name = str(step.get("action_name") or "")
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    try:
        validation = await agent_core_client.validate_action(action_name, params)
    except Exception as exc:
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=str(exc), source="graph_recommend_next_validate_action"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise RuntimeError(f"graph next action contract validation failed: {exc}") from exc

    if validation.get("ok") is False or validation.get("valid") is False:
        errors = validation.get("errors", [])
        error_msg = str(validation.get("error") or ("; ".join(map(str, errors)) if errors else "graph next action contract validation failed"))
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=error_msg, errors=errors, source="graph_recommend_next_validate_action_response"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise RuntimeError(error_msg)

    event_store.append(
        create_event(
            EventType.PLAN_GENERATED,
            request.session_id,
            plan=plan,
            warnings=recommendation.get("warnings", []),
            source="graph_next_suggested_plan",
            recommendation=recommendation,
            ambient_context_attached=bool(ambient_context),
            source_candidate_count=len(ambient_context.get("source_candidates", [])),
        )
    )

    workflow_context = {
        "repo_id": runtime_session.repo_id,
        "worktree_id": runtime_session.worktree_id,
        "allowed_actions": allowed_actions,
        "ambient_context": ambient_context,
        "ambient_prompt_context": ambient_prompt_block,
        "recommendation_source": "graph_recommend_next",
    }
    workflow_adapter = _build_workflow_adapter(session_store=session_store, event_store=event_store, agent_core_client=agent_core_client, worktree_base=worktree_base)
    workflow_result = await workflow_adapter.start_plan(request.session_id, plan, workflow_context)
    if workflow_result.get("started") is not True:
        error_msg = str(workflow_result.get("error") or "workflow adapter did not accept graph plan")
        event_store.append(create_event(EventType.PLAN_VALIDATION_FAILED, request.session_id, error=error_msg, source="graph_workflow_start"))
        session_store.update_status(request.session_id, RuntimeSessionStatus.FAILED)
        raise RuntimeError(error_msg)

    event_store.append(
        create_event(
            EventType.PLAN_STARTED,
            request.session_id,
            backend=workflow_result.get("backend", ""),
            workflow_run_id=workflow_result.get("workflow_run_id", ""),
            ambient_context_attached=bool(ambient_context),
            source="graph_next_suggested_plan",
        )
    )
    session_store.update_status(request.session_id, RuntimeSessionStatus.EDITING)

    return {
        "plan": plan,
        "next_suggested_action": step,
        "recommendation": recommendation,
        "workflow": workflow_result,
        "ambient_context": ambient_context,
        "compatibility_session": runtime_session.to_dict(),
        "message": "Graph work next suggested action wrapped and workflow started.",
    }
