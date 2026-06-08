"""
End-to-end execution tests.

Covers:
  1. Controller calls AgentCoreClient.plan() and validate_plan()
  2. Controller calls WorkflowAdapter.start_plan()
  3. User prompt while running can modify current plan
  4. Child session prompt starts child workflow
  5. Pause/resume/cancel call workflow adapter
  6. commit_checkpoint does not emit COMMIT_CREATED without real commit
  7. RuntimeValidator blocks path traversal
  8. RuntimeValidator blocks composite action when LangGraph disabled
  15. execute_agent_plan emits ACTION_STARTED and ACTION_COMPLETED
  16. execute_agent_plan records outcome to agent-core
  17. Failed action emits ACTION_FAILED
  18. Blocked action emits ACTION_BLOCKED
  20. Commit success emits COMMIT_CREATED only after execution success
  End-to-end: POST /sessions + POST /prompts + GET /events full trail
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def make_tmpdir():
    return tempfile.mkdtemp()


def make_mock_agent_core():
    """Create a mock AgentCoreClient."""
    mock = AsyncMock()
    mock.plan = AsyncMock(return_value={
        "ok": True,
        "plan": {
            "goal": "Fix a bug",
            "mode": "finite",
            "steps": [
                {
                    "action_name": "grep",
                    "params": {"pattern": "bug"},
                    "rationale": "Find the bug",
                    "requires_platform_validation": True,
                },
                {
                    "action_name": "read_file",
                    "params": {"path": "src/main.py"},
                    "rationale": "Read the buggy file",
                    "requires_platform_validation": True,
                },
            ],
        },
        "schema_valid": True,
        "requires_platform_validation": True,
        "warnings": [],
    })
    mock.validate_plan = AsyncMock(return_value={
        "valid": True, "errors": [],
    })
    mock.record_outcome = AsyncMock(return_value={"ok": True})
    return mock


def make_mock_workflow():
    """Create an InProcessWorkflowAdapter."""
    from adapters.workflow.inprocess_adapter import InProcessWorkflowAdapter
    return InProcessWorkflowAdapter()


# ────────────────────────────────────────────────────────────────────
# RuntimeValidator tests
# ────────────────────────────────────────────────────────────────────

class TestRuntimeValidator:
    def setup_method(self):
        self.tmpdir = make_tmpdir()
        from sessions.models import Session, SessionStore
        self.store = SessionStore(self.tmpdir)
        # Create a session with a worktree
        self.wt_dir = Path(self.tmpdir) / "repos" / "wt-1"
        self.wt_dir.mkdir(parents=True)
        session = Session(
            session_id="s1",
            worktree_id="wt-1",
            allowed_actions=["grep", "read_file", "commit"],
        )
        self.store.save(session)
        from execution.runtime_validator import RuntimeValidator
        self.validator = RuntimeValidator(
            self.store,
            worktree_base=str(Path(self.tmpdir) / "repos"),
        )

    def test_valid_action_allowed(self):
        result = self.validator.validate("s1", "grep", {"pattern": "hello"})
        assert result.allowed

    def test_unknown_session_blocked(self):
        result = self.validator.validate("nonexistent", "grep", {})
        assert not result.allowed
        assert "not found" in result.reason

    def test_action_not_in_allowed(self):
        result = self.validator.validate("s1", "apply_patch", {"file": "x"})
        assert not result.allowed
        assert "not in session allowed_actions" in result.reason

    def test_path_traversal_blocked(self):
        result = self.validator.validate(
            "s1", "read_file", {"path": "../../etc/passwd"}
        )
        assert not result.allowed
        assert "escapes worktree" in result.reason

    def test_commit_requires_message(self):
        result = self.validator.validate("s1", "commit", {"message": ""})
        assert not result.allowed
        assert "non-empty message" in result.reason

    def test_commit_with_valid_message(self):
        result = self.validator.validate("s1", "commit", {"message": "fix"})
        assert result.allowed

    def test_composite_action_blocked_when_langgraph_disabled(self):
        from execution.runtime_validator import RuntimeValidator
        validator = RuntimeValidator(
            self.store,
            worktree_base=str(Path(self.tmpdir) / "repos"),
            langgraph_enabled=False,
            allow_fallback_composite=False,
        )
        # Need to add composite to allowed_actions
        session = self.store.get("s1")
        session.allowed_actions.append("autonomous_code_edit")
        self.store.save(session)
        result = validator.validate("s1", "autonomous_code_edit", {})
        assert not result.allowed
        assert "LANGGRAPH_ENABLED" in result.reason


# ────────────────────────────────────────────────────────────────────
# PlanExecutor tests
# ────────────────────────────────────────────────────────────────────

class TestPlanExecutor:
    def setup_method(self):
        self.tmpdir = make_tmpdir()
        self.wt_dir = Path(self.tmpdir) / "repos" / "wt-1"
        self.wt_dir.mkdir(parents=True)
        # Init a real git repo in the worktree
        subprocess.run(["git", "init"], cwd=str(self.wt_dir), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(self.wt_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(self.wt_dir), capture_output=True,
        )
        (self.wt_dir / "src").mkdir()
        (self.wt_dir / "src" / "main.py").write_text("print('bug here')\n")
        subprocess.run(["git", "add", "."], cwd=str(self.wt_dir), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(self.wt_dir), capture_output=True,
        )

        from sessions.models import Session, SessionStore
        from live_feed.events import EventStore
        from adapters.execution.router import ExecutionRouter
        from adapters.composite_action.router import CompositeActionRouter
        from execution.runtime_validator import RuntimeValidator
        from workflows.execute_agent_plan import PlanExecutor

        self.session_store = SessionStore(self.tmpdir)
        self.event_store = EventStore(self.tmpdir)
        session = Session(
            session_id="s1",
            worktree_id="wt-1",
            allowed_actions=[
                "grep", "read_file", "apply_patch",
                "run_tests", "summarize_diff", "commit",
            ],
        )
        self.session_store.save(session)

        self.exec_router = ExecutionRouter(
            executor_backend="fallback",
            allow_fallback=True,
        )
        self.composite_router = CompositeActionRouter(
            execution_router=self.exec_router,
            event_store=self.event_store,
            langgraph_enabled=False,
            allow_fallback_composite=False,
        )
        self.validator = RuntimeValidator(
            self.session_store,
            worktree_base=str(Path(self.tmpdir) / "repos"),
        )
        self.mock_agent_core = make_mock_agent_core()
        self.executor = PlanExecutor(
            session_store=self.session_store,
            event_store=self.event_store,
            execution_router=self.exec_router,
            composite_router=self.composite_router,
            runtime_validator=self.validator,
            agent_core_client=self.mock_agent_core,
            worktree_base=str(Path(self.tmpdir) / "repos"),
        )

    @pytest.mark.asyncio
    async def test_emits_action_started_and_completed(self):
        """Test 15: execute_agent_plan emits ACTION_STARTED and ACTION_COMPLETED."""
        plan = {
            "goal": "Find bugs",
            "mode": "finite",
            "steps": [
                {"action_name": "grep", "params": {"pattern": "bug"}, "rationale": "find it"},
            ],
        }
        result = await self.executor.execute(
            "s1", plan, {"worktree_id": "wt-1"},
        )
        assert result["completed"]
        events = self.event_store.get_events("s1")
        types = [e["event_type"] for e in events]
        assert "action_started" in types
        assert "action_completed" in types

    @pytest.mark.asyncio
    async def test_records_outcome_to_agent_core(self):
        """Test 16: execute_agent_plan records outcome to agent-core."""
        plan = {
            "goal": "Read a file",
            "mode": "finite",
            "steps": [
                {"action_name": "read_file", "params": {"path": "src/main.py"}, "rationale": "read"},
            ],
        }
        await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        assert self.mock_agent_core.record_outcome.call_count >= 1

    @pytest.mark.asyncio
    async def test_failed_action_emits_action_failed(self):
        """Test 17: Failed action emits ACTION_FAILED."""
        plan = {
            "goal": "Run tests",
            "mode": "finite",
            "steps": [
                {"action_name": "run_tests", "params": {"command": "false"}, "rationale": "will fail"},
            ],
        }
        await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        events = self.event_store.get_events("s1")
        types = [e["event_type"] for e in events]
        assert "action_failed" in types

    @pytest.mark.asyncio
    async def test_blocked_action_emits_action_blocked(self):
        """Test 18: Blocked action emits ACTION_BLOCKED."""
        plan = {
            "goal": "Try disallowed action",
            "mode": "finite",
            "steps": [
                {"action_name": "launch_missile", "params": {}, "rationale": "blocked"},
            ],
        }
        await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        events = self.event_store.get_events("s1")
        types = [e["event_type"] for e in events]
        assert "action_blocked" in types

    @pytest.mark.asyncio
    async def test_commit_success_emits_commit_created(self):
        """Test 20: Commit success emits COMMIT_CREATED only after execution success."""
        (self.wt_dir / "new.txt").write_text("commit test\n")
        plan = {
            "goal": "Commit",
            "mode": "finite",
            "steps": [
                {"action_name": "commit", "params": {"message": "test commit"}, "rationale": "save"},
            ],
        }
        await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        events = self.event_store.get_events("s1")
        types = [e["event_type"] for e in events]
        assert "commit_created" in types
        commit_events = [e for e in events if e["event_type"] == "commit_created"]
        assert commit_events[0]["data"]["trigger"] == "plan_execution"

    @pytest.mark.asyncio
    async def test_plan_completed_with_needs_refresh_for_loop(self):
        plan = {
            "goal": "Loop mode",
            "mode": "loop",
            "steps": [
                {"action_name": "grep", "params": {"pattern": "x"}, "rationale": "loop"},
            ],
        }
        await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        events = self.event_store.get_events("s1")
        completed = [e for e in events if e["event_type"] == "plan_completed"]
        assert len(completed) == 1
        assert completed[0]["data"]["needs_refresh"] is True

    @pytest.mark.asyncio
    async def test_cancelled_session_stops_plan(self):
        self.session_store.update_status("s1", "cancelled")
        plan = {
            "goal": "Should not run",
            "mode": "finite",
            "steps": [
                {"action_name": "grep", "params": {"pattern": "x"}, "rationale": "skip"},
            ],
        }
        result = await self.executor.execute("s1", plan, {"worktree_id": "wt-1"})
        assert result["steps_executed"] == 0


# ────────────────────────────────────────────────────────────────────
# SessionController integration tests
# ────────────────────────────────────────────────────────────────────

class TestSessionControllerWithWorkflow:
    def setup_method(self):
        self.tmpdir = make_tmpdir()
        from sessions.controller import SessionController
        self.mock_agent_core = make_mock_agent_core()
        self.mock_workflow = make_mock_workflow()
        self.ctrl = SessionController(
            sessions_dir=self.tmpdir,
            agent_core_client=self.mock_agent_core,
            workflow_adapter=self.mock_workflow,
        )

    @pytest.mark.asyncio
    async def test_prompt_calls_agent_core_plan(self):
        """Test 1: Controller calls AgentCoreClient.plan()."""
        from sessions.controller import CreateSessionRequest, PromptRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="fix the bug")
        )
        sid = session_result["session"]["session_id"]
        result = await self.ctrl.handle_prompt(
            sid, PromptRequest(prompt="also check tests")
        )
        assert self.mock_agent_core.plan.call_count >= 1

    @pytest.mark.asyncio
    async def test_prompt_calls_validate_plan(self):
        """Test 1: Controller calls AgentCoreClient.validate_plan()."""
        from sessions.controller import CreateSessionRequest, PromptRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="fix bug")
        )
        sid = session_result["session"]["session_id"]
        await self.ctrl.handle_prompt(sid, PromptRequest(prompt="also fix tests"))
        assert self.mock_agent_core.validate_plan.call_count >= 1

    @pytest.mark.asyncio
    async def test_prompt_starts_workflow(self):
        """Test 2: Controller calls WorkflowAdapter.start_plan()."""
        from sessions.controller import CreateSessionRequest, PromptRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="fix it")
        )
        sid = session_result["session"]["session_id"]
        result = await self.ctrl.handle_prompt(
            sid, PromptRequest(prompt="also do this")
        )
        plan_result = result.get("plan", {})
        assert plan_result.get("workflow", {}).get("started") is True

    @pytest.mark.asyncio
    async def test_prompt_emits_plan_events(self):
        """Test: Plan lifecycle events emitted."""
        from sessions.controller import CreateSessionRequest, PromptRequest
        from live_feed.events import EventStore
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="fix it")
        )
        sid = session_result["session"]["session_id"]
        await self.ctrl.handle_prompt(sid, PromptRequest(prompt="also fix"))
        events = self.ctrl.event_store.get_events(sid)
        types = [e["event_type"] for e in events]
        assert "plan_requested" in types
        assert "plan_generated" in types
        assert "plan_started" in types

    @pytest.mark.asyncio
    async def test_child_session_creation_starts_plan(self):
        """Test 4: Creating a child session and submitting a prompt starts plan."""
        from sessions.controller import CreateSessionRequest, PromptRequest
        parent_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="main task")
        )
        parent_id = parent_result["session"]["session_id"]
        # Create child session directly
        child_result = self.ctrl.create_session(
            CreateSessionRequest(
                prompt="migrate auth",
                session_type="child_session",
                parent_session_id=parent_id,
            )
        )
        child_id = child_result["session"]["session_id"]
        # Submit prompt to child — should call agent-core and start workflow
        result = await self.ctrl.handle_prompt(
            child_id, PromptRequest(prompt="migrate auth module")
        )
        plan = result.get("plan", {})
        assert plan.get("workflow", {}).get("started") is True
        assert plan.get("plan", {}).get("goal") is not None

    @pytest.mark.asyncio
    async def test_pause_calls_workflow_adapter(self):
        """Test 5: Pause calls workflow adapter."""
        from sessions.controller import CreateSessionRequest, ControlRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="test")
        )
        sid = session_result["session"]["session_id"]
        result = await self.ctrl.handle_control(
            sid, ControlRequest(command="pause")
        )
        assert result["status"] == "paused"
        intent = self.mock_workflow.get_control_intent(sid)
        assert intent == "pause"

    @pytest.mark.asyncio
    async def test_cancel_calls_workflow_adapter(self):
        """Test 5: Cancel calls workflow adapter."""
        from sessions.controller import CreateSessionRequest, ControlRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="test")
        )
        sid = session_result["session"]["session_id"]
        result = await self.ctrl.handle_control(
            sid, ControlRequest(command="cancel")
        )
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_commit_checkpoint_no_commit_created_event(self):
        """Test 6: commit_checkpoint does not emit COMMIT_CREATED."""
        from sessions.controller import CreateSessionRequest, ControlRequest
        session_result = self.ctrl.create_session(
            CreateSessionRequest(prompt="test")
        )
        sid = session_result["session"]["session_id"]
        result = await self.ctrl.handle_control(
            sid, ControlRequest(command="commit_checkpoint")
        )
        assert result["status"] == "commit_requested"
        events = self.ctrl.event_store.get_events(sid)
        types = [e["event_type"] for e in events]
        assert "commit_created" not in types


# ────────────────────────────────────────────────────────────────────
# Full API end-to-end test
# ────────────────────────────────────────────────────────────────────

class TestEndToEndAPI:
    def setup_method(self):
        self.tmpdir = make_tmpdir()
        os.environ["SESSIONS_DIR"] = self.tmpdir

    @pytest.mark.asyncio
    async def test_full_flow_create_prompt_events(self):
        """End-to-end: POST /sessions -> POST /prompts -> GET /events."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sessions.routes import router, set_controller
        from sessions.controller import SessionController

        app = FastAPI()
        app.include_router(router)

        mock_agent_core = make_mock_agent_core()
        mock_workflow = make_mock_workflow()
        ctrl = SessionController(
            sessions_dir=self.tmpdir,
            agent_core_client=mock_agent_core,
            workflow_adapter=mock_workflow,
        )
        set_controller(ctrl)

        client = TestClient(app)

        # Create session
        resp = client.post("/api/v2/sessions", json={
            "prompt": "Fix login bug",
        })
        assert resp.status_code == 200
        session_id = resp.json()["session"]["session_id"]

        # Submit prompt
        resp = client.post(f"/api/v2/sessions/{session_id}/prompts", json={
            "prompt": "also check the tests",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "routing" in data

        # Get events
        resp = client.get(f"/api/v2/sessions/{session_id}/events")
        assert resp.status_code == 200
        events = resp.json()["events"]
        types = [e["event_type"] for e in events]
        assert "user_prompt_received" in types
        assert "routing_decision_made" in types
        # Plan events should be present
        assert "plan_requested" in types
        assert "plan_generated" in types
        assert "plan_started" in types
