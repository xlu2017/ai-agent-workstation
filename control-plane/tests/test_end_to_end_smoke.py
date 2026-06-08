"""
End-to-end smoke tests for the control-plane prompt flow.

Tests the full path: session create → prompt submit → routing → execution → events.
Uses mocked OpenHands and agent-core to verify integration without live services.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure control-plane is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test-mode env vars — only SESSIONS_DIR and ROUTER; avoid leaking executor config
_TEST_SESSIONS_DIR = tempfile.mkdtemp()
os.environ["SESSIONS_DIR"] = _TEST_SESSIONS_DIR
os.environ.setdefault("ROUTER_LLM_ENABLED", "false")

SESSIONS_DIR = Path(_TEST_SESSIONS_DIR)


def _create_test_session(session_id: str = "smoke-test-001"):
    """Create a minimal session directory for testing."""
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "events").mkdir(exist_ok=True)
    meta = {
        "id": session_id,
        "branch": "test-branch",
        "worktree_path": str(session_dir / "worktree"),
        "status": "active",
    }
    (session_dir / "meta.json").write_text(json.dumps(meta))
    # Create worktree dir
    wt = session_dir / "worktree"
    wt.mkdir(exist_ok=True)
    (wt / "README.md").write_text("# Test Repo\nHello world.")
    return session_id


class TestPromptHandler:
    """Test the prompt handler end-to-end flow."""

    def setup_method(self):
        self.session_id = _create_test_session()

    @pytest.mark.asyncio
    async def test_prompt_emits_events(self):
        """Submitting a prompt should produce events in events.jsonl."""
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy

        # Use permissive policy for testing
        policy = RuntimePolicy(
            commit_requires_approval=False,
            push_requires_approval=False,
        )

        # Patch _sessions_dir to point to our test dir
        with patch("execution.prompt_handler._sessions_dir", return_value=SESSIONS_DIR):
            # Mock OpenHands to avoid real network calls
            with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
                mock_exec.return_value = {
                    "status": "completed",
                    "summary": "Inspected README and summarized it",
                    "files_edited": [],
                    "duration_seconds": 2.5,
                }

                result = await handle_prompt(
                    session_id=self.session_id,
                    instruction="Inspect the repo and summarize the README. Do not edit files.",
                    use_agent_core=False,
                    policy=policy,
                )

        assert result.state == TaskState.COMPLETED
        assert result.task_id.startswith("task-")
        assert result.session_id == self.session_id
        assert result.routing_decision != ""

        # Check events were written
        events_path = SESSIONS_DIR / self.session_id / "events" / "events.jsonl"
        assert events_path.exists()
        events = [json.loads(l) for l in events_path.read_text().strip().split("\n") if l.strip()]
        assert len(events) >= 3  # prompt_received, routing, action_started, action_completed
        types = [e.get("event_type") for e in events]
        assert "user_prompt_received" in types
        assert "routing_decision_made" in types

    @pytest.mark.asyncio
    async def test_blocked_command_detected(self):
        """Commands matching blocked patterns should be rejected."""
        from execution.prompt_handler import handle_prompt, TaskState

        with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
            result = await handle_prompt(
                session_id=self.session_id,
                instruction="rm -rf / and clean everything",
                use_agent_core=False,
            )

        assert result.state == TaskState.BLOCKED
        assert "Blocked command" in result.message
        # OpenHands should NOT have been called
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_openhands_unavailable_returns_blocked(self):
        """When OpenHands is unreachable, state should be blocked/failed, not silent."""
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy

        policy = RuntimePolicy(commit_requires_approval=False)

        with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
            mock_exec.return_value = {
                "status": "blocked",
                "summary": "OpenHands unreachable: Connection refused",
                "files_edited": [],
                "duration_seconds": 0,
            }

            result = await handle_prompt(
                session_id=self.session_id,
                instruction="Read the README file",
                use_agent_core=False,
                policy=policy,
            )

        assert result.state == TaskState.BLOCKED
        assert "OpenHands" in result.message or "unreachable" in result.message

    @pytest.mark.asyncio
    async def test_agent_core_unavailable_proceeds(self):
        """If agent-core is down, execution should still proceed (non-fatal)."""
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy

        policy = RuntimePolicy(commit_requires_approval=False)

        with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
            mock_exec.return_value = {
                "status": "completed",
                "summary": "Done",
                "files_edited": [],
                "duration_seconds": 1.0,
            }

            result = await handle_prompt(
                session_id=self.session_id,
                instruction="Read the README",
                use_agent_core=True,  # will fail but should not block
                policy=policy,
            )

        assert result.state == TaskState.COMPLETED

    @pytest.mark.asyncio
    async def test_interrupt_routing(self):
        """Control commands should be routed as interrupt."""
        from execution.prompt_handler import handle_prompt, TaskState

        result = await handle_prompt(
            session_id=self.session_id,
            instruction="stop",
            use_agent_core=False,
        )

        assert result.state == TaskState.COMPLETED
        assert result.routing_decision == "interrupt_current"

    @pytest.mark.asyncio
    async def test_nonexistent_session_blocked(self):
        """Prompt to a non-existent session should be blocked."""
        from execution.prompt_handler import handle_prompt, TaskState

        result = await handle_prompt(
            session_id="does-not-exist-xyz",
            instruction="do something",
            use_agent_core=False,
        )

        # Should be blocked or failed — not successful
        assert result.state in (TaskState.BLOCKED, TaskState.FAILED)
        assert result.error or result.message


class TestTaskState:
    """Test truthful state derivation from events."""

    def setup_method(self):
        self.session_id = _create_test_session("state-test-001")

    def test_empty_events_returns_session_created(self):
        from execution.prompt_handler import get_task_state
        state = get_task_state(self.session_id)
        # No events yet — either session_created or unknown is acceptable
        assert state["state"] in ("session_created", "unknown")

    def test_state_after_prompt(self):
        from execution.prompt_handler import get_task_state, _emit_event
        _emit_event(self.session_id, "user_prompt_received", "test prompt")
        state = get_task_state(self.session_id)
        assert state["state"] == "prompt_received"

    def test_state_after_completion(self):
        from execution.prompt_handler import get_task_state, _emit_event
        _emit_event(self.session_id, "user_prompt_received", "test")
        _emit_event(self.session_id, "action_started", "starting")
        _emit_event(self.session_id, "action_completed", "done")
        state = get_task_state(self.session_id)
        assert state["state"] == "completed"
        assert state["total_events"] >= 3

    def test_state_after_failure(self):
        from execution.prompt_handler import get_task_state, _emit_event
        _emit_event(self.session_id, "action_failed", "error occurred")
        state = get_task_state(self.session_id)
        assert state["state"] == "failed"


class TestAPIEndpoints:
    """Test the FastAPI chat/state/events endpoints."""

    def setup_method(self):
        self.session_id = _create_test_session("api-test-001")

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "disk" in data or "memory" in data

    def test_create_and_list_sessions(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert "sessions" in resp.json()

    def test_events_endpoint_empty(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)
        resp = client.get(f"/api/sessions/{self.session_id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data

    def test_state_endpoint(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)
        resp = client.get(f"/api/sessions/{self.session_id}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data

    def test_chat_endpoint_with_mock(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)

        with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
            mock_exec.return_value = {
                "status": "completed",
                "summary": "Done",
                "files_edited": [],
                "duration_seconds": 1.0,
            }
            resp = client.post(
                f"/api/sessions/{self.session_id}/chat",
                json={"instruction": "Read README"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "completed"
        assert data["task_id"].startswith("task-")
        assert data["session_id"] == self.session_id

    def test_chat_blocked_returns_state(self):
        from fastapi.testclient import TestClient
        from api.server import app
        client = TestClient(app)

        resp = client.post(
            f"/api/sessions/{self.session_id}/chat",
            json={"instruction": "rm -rf / destroy everything"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "blocked"
        assert "Blocked command" in data["message"]


class TestRuntimePolicy:
    """Test runtime policy enforcement."""

    def setup_method(self):
        self.session_id = _create_test_session("policy-test-001")

    @pytest.mark.asyncio
    async def test_commit_requires_approval(self):
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy
        policy = RuntimePolicy(commit_requires_approval=True)

        with patch("execution.prompt_handler._execute_via_openhands"):
            result = await handle_prompt(
                session_id=self.session_id,
                instruction="commit the changes now",
                use_agent_core=False,
                policy=policy,
            )
        assert result.state == TaskState.BLOCKED
        assert "approval" in result.message.lower()

    @pytest.mark.asyncio
    async def test_push_requires_approval(self):
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy
        policy = RuntimePolicy(push_requires_approval=True)

        with patch("execution.prompt_handler._execute_via_openhands"):
            result = await handle_prompt(
                session_id=self.session_id,
                instruction="push to origin main",
                use_agent_core=False,
                policy=policy,
            )
        assert result.state == TaskState.BLOCKED
        assert "approval" in result.message.lower()

    @pytest.mark.asyncio
    async def test_safe_prompt_allowed(self):
        from execution.prompt_handler import handle_prompt, TaskState, RuntimePolicy
        policy = RuntimePolicy(commit_requires_approval=False)

        with patch("execution.prompt_handler._execute_via_openhands") as mock_exec:
            mock_exec.return_value = {
                "status": "completed",
                "summary": "Read the file",
                "files_edited": [],
                "duration_seconds": 0.5,
            }
            result = await handle_prompt(
                session_id=self.session_id,
                instruction="read the config file",
                use_agent_core=False,
                policy=policy,
            )
        assert result.state == TaskState.COMPLETED


class TestOpenHandsIntegration:
    """Test OpenHands adapter integration points."""

    def test_adapter_has_is_available(self):
        from executors.openhands_adapter import OpenHandsExecutorAdapter
        adapter = OpenHandsExecutorAdapter()
        # In test env, OpenHands is likely unavailable
        result = adapter.is_available()
        assert isinstance(result, bool)

    def test_adapter_run_task_returns_task_result(self):
        from executors.openhands_adapter import OpenHandsExecutorAdapter
        from executors.base import TaskPacket, TaskResult

        # Override SESSIONS_DIR for test
        test_sessions = Path(os.environ["SESSIONS_DIR"])
        with patch("executors.openhands_adapter.SESSIONS_DIR", test_sessions):
            adapter = OpenHandsExecutorAdapter()
            packet = TaskPacket(
                task_id="test-1",
                session_id="test-session",
                instruction="hello",
                worktree_path="/nonexistent/path",
                branch="test",
            )
            result = adapter.run_task("test-session", packet)
        assert isinstance(result, TaskResult)
        # Should fail because worktree doesn't exist
        assert result.status == "failed"
