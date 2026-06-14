import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import SessionKind, SessionRecord, SessionStatus  # noqa: E402
from api.services.session_graph_execution_bridge import (  # noqa: E402
    build_graph_work_execution_readiness_request,
    build_graph_work_initial_execution_scaffold,
    record_execution_readiness_on_work_session,
    scaffold_execution_readiness_result,
    should_mark_graph_work_execution_ready,
)
from execution.activation import (  # noqa: E402
    ExecutionActivationRequest,
    ExecutionActivationService,
    ExecutionActivationSource,
    ExecutionActivationStatus,
)


def test_activation_service_never_autostarts_without_repo_context():
    service = ExecutionActivationService()
    result = asyncio.run(
        service.activate(
            ExecutionActivationRequest(
                session_id="work-1",
                prompt="Fix the bug",
                source=ExecutionActivationSource.SESSION_GRAPH_CHAT,
            )
        )
    )

    assert result.status == ExecutionActivationStatus.BLOCKED_NEEDS_REPO
    assert result.auto_started is False


def test_activation_service_never_autostarts_without_workflow_callback():
    service = ExecutionActivationService()
    result = asyncio.run(
        service.activate(
            ExecutionActivationRequest(
                session_id="work-1",
                prompt="Fix the bug",
                source=ExecutionActivationSource.SESSION_GRAPH_CHAT,
                repo_context_id="repo-1",
            )
        )
    )

    assert result.status == ExecutionActivationStatus.READY_NOT_STARTED
    assert result.auto_started is False


def test_activation_service_marks_started_only_after_callback_success():
    async def start_workflow(request: ExecutionActivationRequest) -> dict[str, object]:
        return {"workflow": {"workflow_run_id": f"run-{request.session_id}"}}

    service = ExecutionActivationService(start_workflow=start_workflow)
    result = asyncio.run(
        service.activate(
            ExecutionActivationRequest(
                session_id="work-1",
                prompt="Fix the bug",
                source=ExecutionActivationSource.SESSION_GRAPH_CHAT,
                repo_context_id="repo-1",
            )
        )
    )

    assert result.status == ExecutionActivationStatus.STARTED
    assert result.auto_started is True
    assert result.workflow == {"workflow_run_id": "run-work-1"}


def test_graph_work_execution_readiness_request_uses_parent_repo_context():
    parent = SessionRecord(
        id="goal-1",
        kind=SessionKind.GOAL,
        title="Goal",
        status=SessionStatus.ACTIVE,
        metadata={"repo_session_id": "repo-session-1"},
    )
    work = SessionRecord(
        id="work-1",
        kind=SessionKind.WORK,
        title="Work",
        status=SessionStatus.ACTIVE,
        parent_id="goal-1",
        root_id="goal-1",
        facets={"work": {"prompt": "Run validation", "execution_state": "ready_for_execution", "requires_execution_start": True, "auto_started": False}},
    )

    assert should_mark_graph_work_execution_ready(work) is True
    request = build_graph_work_execution_readiness_request(work_session=work, parent_session=parent)

    assert request.session_id == "work-1"
    assert request.parent_session_id == "goal-1"
    assert request.repo_context_id == "repo-session-1"
    assert request.prompt == "Run validation"


def test_graph_work_initial_execution_scaffold_has_first_context_action_then_llm_gate():
    request = ExecutionActivationRequest(
        session_id="work-1",
        prompt="Why is the world round?",
        source=ExecutionActivationSource.SESSION_GRAPH_CHAT,
        repo_context_id="repo-session-1",
    )

    scaffold = build_graph_work_initial_execution_scaffold(request)

    assert scaffold["executor_start"]["status"] == "pending_adapter"
    assert scaffold["executor_start"]["auto_started"] is False
    assert len(scaffold["steps"]) == 1
    assert scaffold["steps"][0]["decision"] == "find_out_more"
    assert scaffold["steps"][0]["task_name"] == "search_code"
    assert scaffold["steps"][0]["params"]["query"] == "Why is the world round?"
    assert scaffold["steps"][0]["params"]["scope"] == "repo-session-1"
    assert scaffold["after_step"]["requires_llm_after_outcome"] is True
    assert scaffold["after_step"]["max_top_level_actions_before_next_llm"] == 1


def test_graph_work_records_non_starting_execution_readiness_result():
    work = SessionRecord(
        id="work-1",
        kind=SessionKind.WORK,
        title="Work",
        status=SessionStatus.ACTIVE,
        parent_id="goal-1",
        root_id="goal-1",
        facets={"work": {"prompt": "Run validation", "execution_state": "ready_for_execution", "requires_execution_start": True, "auto_started": False}},
    )
    request = build_graph_work_execution_readiness_request(work_session=work, parent_session=None)
    result = scaffold_execution_readiness_result(request)
    record_execution_readiness_on_work_session(work, result)

    assert work.state["execution_readiness"]["status"] == "blocked_needs_repo"
    assert work.state["execution_readiness"]["auto_started"] is False
    assert work.facets["work"]["execution_readiness"]["auto_started"] is False


def test_graph_work_records_ready_execution_readiness_scaffold_when_repo_context_exists():
    parent = SessionRecord(
        id="goal-1",
        kind=SessionKind.GOAL,
        title="Goal",
        status=SessionStatus.ACTIVE,
        metadata={"repo_session_id": "repo-session-1"},
    )
    work = SessionRecord(
        id="work-1",
        kind=SessionKind.WORK,
        title="Work",
        status=SessionStatus.ACTIVE,
        parent_id="goal-1",
        root_id="goal-1",
        facets={"work": {"prompt": "Why is the world round?", "execution_state": "ready_for_execution", "requires_execution_start": True, "auto_started": False}},
    )

    request = build_graph_work_execution_readiness_request(work_session=work, parent_session=parent)
    result = scaffold_execution_readiness_result(request)
    record_execution_readiness_on_work_session(work, result)

    readiness = work.state["execution_readiness"]
    assert readiness["status"] == "ready_not_started"
    assert readiness["auto_started"] is False
    assert readiness["initial_execution_scaffold"]["steps"][0]["task_name"] == "search_code"
    assert readiness["initial_execution_scaffold"]["after_step"]["requires_llm_after_outcome"] is True
    assert readiness["executor"]["status"] == "not_started"
    assert readiness["metadata"]["executor_start_scaffolded"] is True
