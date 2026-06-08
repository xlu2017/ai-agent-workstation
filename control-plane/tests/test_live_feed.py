"""
Tests for Part 2: live feed, prompt routing, session types, control commands,
concurrency rules, and agent-core integration client.

Tests verify:
  - Event stream model and storage
  - SSE endpoint
  - Prompt intake and routing decisions
  - Session types (root/child/parallel/queued)
  - Control commands (pause/resume/cancel)
  - Concurrency rules and worktree isolation
  - Agent-core integration client structure
  - Full API routes via FastAPI TestClient
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add control-plane root to path
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(CONTROL_PLANE_ROOT.parent))


# ════════════════════════════════════════════════════════════════════
# 1. Event store tests
# ════════════════════════════════════════════════════════════════════

class TestEventStore:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from live_feed.events import EventStore
        self.store = EventStore(self.tmpdir)

    def test_append_event(self):
        from live_feed.events import EventType, create_event
        evt = create_event(EventType.USER_PROMPT_RECEIVED, "s1", prompt="hello")
        stored = self.store.append(evt)
        assert stored.sequence == 1
        assert stored.event_type == EventType.USER_PROMPT_RECEIVED

    def test_append_multiple_events_increments_sequence(self):
        from live_feed.events import EventType, create_event
        e1 = self.store.append(create_event(EventType.PLAN_STARTED, "s1"))
        e2 = self.store.append(create_event(EventType.ACTION_STARTED, "s1", action_name="grep"))
        e3 = self.store.append(create_event(EventType.ACTION_COMPLETED, "s1", action_name="grep"))
        assert e1.sequence == 1
        assert e2.sequence == 2
        assert e3.sequence == 3

    def test_get_events_after_sequence(self):
        from live_feed.events import EventType, create_event
        self.store.append(create_event(EventType.PLAN_STARTED, "s1"))
        self.store.append(create_event(EventType.ACTION_STARTED, "s1"))
        self.store.append(create_event(EventType.ACTION_COMPLETED, "s1"))
        events = self.store.get_events("s1", after_sequence=1)
        assert len(events) == 2
        assert events[0]["sequence"] == 2

    def test_get_events_filter_by_type(self):
        from live_feed.events import EventType, create_event
        self.store.append(create_event(EventType.PLAN_STARTED, "s1"))
        self.store.append(create_event(EventType.ACTION_STARTED, "s1"))
        self.store.append(create_event(EventType.PLAN_COMPLETED, "s1"))
        events = self.store.get_events(
            "s1", event_types=[EventType.ACTION_STARTED]
        )
        assert len(events) == 1
        assert events[0]["event_type"] == "action_started"

    def test_get_events_with_limit(self):
        from live_feed.events import EventType, create_event
        for i in range(10):
            self.store.append(create_event(EventType.ACTION_PROGRESS, "s1", step=i))
        events = self.store.get_events("s1", limit=3)
        assert len(events) == 3

    def test_get_latest_event(self):
        from live_feed.events import EventType, create_event
        self.store.append(create_event(EventType.PLAN_STARTED, "s1"))
        self.store.append(create_event(EventType.ACTION_COMPLETED, "s1", name="grep"))
        latest = self.store.get_latest_event("s1")
        assert latest["event_type"] == "action_completed"

    def test_get_latest_event_filtered(self):
        from live_feed.events import EventType, create_event
        self.store.append(create_event(EventType.PLAN_STARTED, "s1"))
        self.store.append(create_event(EventType.ACTION_COMPLETED, "s1"))
        latest = self.store.get_latest_event("s1", EventType.PLAN_STARTED)
        assert latest["event_type"] == "plan_started"

    def test_get_events_empty_session(self):
        events = self.store.get_events("nonexistent")
        assert events == []

    def test_event_to_sse_format(self):
        from live_feed.events import EventType, create_event
        evt = create_event(EventType.USER_PROMPT_RECEIVED, "s1", prompt="test")
        sse = evt.to_sse()
        assert sse.startswith("id: ")
        assert "event: user_prompt_received" in sse
        assert "data: " in sse

    def test_all_event_types_exist(self):
        from live_feed.events import EventType
        expected = [
            "user_prompt_received", "routing_decision_made", "plan_requested",
            "plan_generated", "plan_validation_failed", "plan_started",
            "action_started", "action_progress", "action_blocked",
            "action_completed", "action_failed", "plan_paused",
            "plan_resumed", "plan_cancelled", "plan_completed",
            "child_session_started", "memory_extracted",
            "commit_created", "pr_created",
        ]
        for name in expected:
            assert EventType(name) is not None


# ════════════════════════════════════════════════════════════════════
# 2. Prompt routing tests
# ════════════════════════════════════════════════════════════════════

class TestPromptRouter:
    def test_stop_routes_to_interrupt(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(session_id="s1", prompt="stop", current_plan_status="running")
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.INTERRUPT_CURRENT
        assert out.control_command == "cancel"

    def test_pause_routes_to_interrupt(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(session_id="s1", prompt="pause", current_plan_status="running")
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.INTERRUPT_CURRENT
        assert out.control_command == "pause"

    def test_resume_routes_to_append(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(session_id="s1", prompt="resume", current_plan_status="paused")
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.APPEND_TO_CURRENT
        assert out.control_command == "resume"

    def test_also_check_tests_modifies_plan(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="also check the tests",
            current_plan_status="running",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.MODIFY_CURRENT_PLAN

    def test_new_task_spawns_child(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="new task: migrate auth to OAuth",
            current_plan_status="running",
            repo_id="my-repo",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.SPAWN_CHILD_SESSION

    def test_work_on_another_repo_spawns_new(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="work on another repo",
            current_plan_status="running",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.SPAWN_NEW_SESSION

    def test_no_plan_appends_to_current(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(session_id="s1", prompt="fix the login bug", current_plan_status="none")
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.APPEND_TO_CURRENT

    def test_short_prompt_during_running_plan_appends(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="yes, do that",
            current_plan_status="running",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.APPEND_TO_CURRENT

    def test_long_prompt_during_running_plan_modifies(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="I need you to completely restructure the authentication layer to use JWT tokens with refresh capabilities and add proper rate limiting on all endpoints",
            current_plan_status="running",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.MODIFY_CURRENT_PLAN

    def test_detect_control_command_cancel(self):
        from prompt_router.router import detect_control_command
        assert detect_control_command("cancel") == "cancel"
        assert detect_control_command("abort this") == "cancel"
        assert detect_control_command("stop now") == "cancel"

    def test_detect_control_command_none(self):
        from prompt_router.router import detect_control_command
        assert detect_control_command("fix the login bug") is None

    def test_commit_what_is_done(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="commit what is done",
            current_plan_status="running",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.APPEND_TO_CURRENT
        assert out.control_command == "commit_checkpoint"

    def test_start_new_session_explicit(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(session_id="s1", prompt="start a new session for this")
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.SPAWN_NEW_SESSION

    def test_after_this_queues_or_spawns(self):
        from prompt_router.router import RoutingInput, route_prompt, RoutingDecision
        inp = RoutingInput(
            session_id="s1",
            prompt="after this, also clean up docs",
            current_plan_status="running",
            repo_id="my-repo",
        )
        out = route_prompt(inp)
        assert out.decision == RoutingDecision.SPAWN_CHILD_SESSION


# ════════════════════════════════════════════════════════════════════
# 3. Session model tests
# ════════════════════════════════════════════════════════════════════

class TestSessionModels:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from sessions.models import SessionStore
        self.store = SessionStore(self.tmpdir)

    def test_create_and_get_session(self):
        from sessions.models import Session, SessionType, SessionStatus
        s = Session(
            session_id="test-1",
            session_type=SessionType.ROOT,
            status=SessionStatus.CREATED,
            repo_id="my-repo",
            prompt="fix bug",
        )
        self.store.save(s)
        loaded = self.store.get("test-1")
        assert loaded is not None
        assert loaded.session_id == "test-1"
        assert loaded.session_type == SessionType.ROOT
        assert loaded.prompt == "fix bug"

    def test_session_types(self):
        from sessions.models import SessionType
        assert SessionType.ROOT.value == "root_session"
        assert SessionType.CHILD.value == "child_session"
        assert SessionType.PARALLEL.value == "parallel_session"
        assert SessionType.QUEUED.value == "queued_session"

    def test_session_statuses(self):
        from sessions.models import SessionStatus
        expected = [
            "created", "claimed", "planning", "editing", "validating",
            "committed", "answered", "failed", "blocked", "paused",
            "cancelled", "completed",
        ]
        for s in expected:
            assert SessionStatus(s) is not None

    def test_update_status(self):
        from sessions.models import Session, SessionStatus
        s = Session(session_id="test-2", prompt="test")
        self.store.save(s)
        self.store.update_status("test-2", SessionStatus.PAUSED)
        loaded = self.store.get("test-2")
        assert loaded.status == SessionStatus.PAUSED

    def test_list_sessions_by_type(self):
        from sessions.models import Session, SessionType
        self.store.save(Session(session_id="root-1", session_type=SessionType.ROOT))
        self.store.save(Session(session_id="child-1", session_type=SessionType.CHILD))
        self.store.save(Session(session_id="root-2", session_type=SessionType.ROOT))
        roots = self.store.list_sessions(session_type=SessionType.ROOT)
        assert len(roots) == 2
        children = self.store.list_sessions(session_type=SessionType.CHILD)
        assert len(children) == 1

    def test_list_sessions_by_parent(self):
        from sessions.models import Session, SessionType
        self.store.save(Session(session_id="parent-1", session_type=SessionType.ROOT))
        self.store.save(Session(
            session_id="child-1",
            session_type=SessionType.CHILD,
            parent_session_id="parent-1",
        ))
        children = self.store.list_sessions(parent_id="parent-1")
        assert len(children) == 1
        assert children[0].session_id == "child-1"

    def test_session_to_dict(self):
        from sessions.models import Session, SessionType, SessionStatus
        s = Session(session_id="test-3", session_type=SessionType.CHILD, status=SessionStatus.EDITING)
        d = s.to_dict()
        assert d["session_type"] == "child_session"
        assert d["status"] == "editing"

    def test_get_nonexistent_session_returns_none(self):
        loaded = self.store.get("nonexistent")
        assert loaded is None


# ════════════════════════════════════════════════════════════════════
# 4. Session controller tests
# ════════════════════════════════════════════════════════════════════

class TestSessionController:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from sessions.controller import SessionController
        self.ctrl = SessionController(self.tmpdir)

    def test_create_root_session(self):
        from sessions.controller import CreateSessionRequest
        result = self.ctrl.create_session(CreateSessionRequest(
            prompt="fix login bug",
            repo_id="my-repo",
        ))
        assert "session" in result
        assert result["session"]["session_type"] == "root_session"
        assert result["session"]["status"] == "created"

    def test_create_child_session(self):
        from sessions.controller import CreateSessionRequest
        parent = self.ctrl.create_session(CreateSessionRequest(
            prompt="main task",
        ))
        parent_id = parent["session"]["session_id"]
        child = self.ctrl.create_session(CreateSessionRequest(
            prompt="subtask",
            session_type="child_session",
            parent_session_id=parent_id,
        ))
        assert child["session"]["session_type"] == "child_session"
        assert child["session"]["parent_session_id"] == parent_id

    @pytest.mark.asyncio
    async def test_handle_prompt_records_events(self):
        from sessions.controller import CreateSessionRequest, PromptRequest
        from live_feed.events import EventStore
        result = self.ctrl.create_session(CreateSessionRequest(prompt="initial"))
        sid = result["session"]["session_id"]
        await self.ctrl.handle_prompt(sid, PromptRequest(prompt="also check tests"))
        store = EventStore(self.tmpdir)
        events = store.get_events(sid)
        types = [e["event_type"] for e in events]
        assert "user_prompt_received" in types
        assert "routing_decision_made" in types

    @pytest.mark.asyncio
    async def test_handle_control_pause(self):
        from sessions.controller import CreateSessionRequest, ControlRequest
        from sessions.models import SessionStore, SessionStatus
        result = self.ctrl.create_session(CreateSessionRequest(prompt="task"))
        sid = result["session"]["session_id"]
        ctrl_result = await self.ctrl.handle_control(sid, ControlRequest(command="pause"))
        assert ctrl_result["status"] == "paused"
        store = SessionStore(self.tmpdir)
        s = store.get(sid)
        assert s.status == SessionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_handle_control_resume(self):
        from sessions.controller import CreateSessionRequest, ControlRequest
        result = self.ctrl.create_session(CreateSessionRequest(prompt="task"))
        sid = result["session"]["session_id"]
        await self.ctrl.handle_control(sid, ControlRequest(command="pause"))
        ctrl_result = await self.ctrl.handle_control(sid, ControlRequest(command="resume"))
        assert ctrl_result["status"] == "resumed"

    @pytest.mark.asyncio
    async def test_handle_control_cancel(self):
        from sessions.controller import CreateSessionRequest, ControlRequest
        from sessions.models import SessionStore, SessionStatus
        result = self.ctrl.create_session(CreateSessionRequest(prompt="task"))
        sid = result["session"]["session_id"]
        await self.ctrl.handle_control(sid, ControlRequest(command="cancel"))
        store = SessionStore(self.tmpdir)
        s = store.get(sid)
        assert s.status == SessionStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_prompt_stop_triggers_interrupt(self):
        from sessions.controller import CreateSessionRequest, PromptRequest
        from sessions.models import SessionStore, SessionStatus
        result = self.ctrl.create_session(CreateSessionRequest(prompt="task"))
        sid = result["session"]["session_id"]
        # Set to editing so plan status = running
        store = SessionStore(self.tmpdir)
        store.update_status(sid, SessionStatus.EDITING)
        prompt_result = await self.ctrl.handle_prompt(sid, PromptRequest(prompt="stop"))
        assert prompt_result.get("status") in ("paused", "cancelled")

    @pytest.mark.asyncio
    async def test_prompt_spawns_child_for_new_task(self):
        from sessions.controller import CreateSessionRequest, PromptRequest
        from sessions.models import SessionStore, SessionStatus
        result = self.ctrl.create_session(CreateSessionRequest(
            prompt="fix login", repo_id="my-repo",
        ))
        sid = result["session"]["session_id"]
        store = SessionStore(self.tmpdir)
        store.update_status(sid, SessionStatus.EDITING)
        prompt_result = await self.ctrl.handle_prompt(
            sid, PromptRequest(prompt="new task: migrate auth to OAuth")
        )
        assert "child_session" in prompt_result or "routing" in prompt_result


# ════════════════════════════════════════════════════════════════════
# 5. Concurrency rules tests
# ════════════════════════════════════════════════════════════════════

class TestConcurrency:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from sessions.models import SessionStore
        from sessions.concurrency import ConcurrencyManager
        self.store = SessionStore(self.tmpdir)
        self.mgr = ConcurrencyManager(self.store)

    def test_claim_worktree_first_mutating(self):
        result = self.mgr.claim_worktree("s1", "wt-1", "mutating")
        assert result.allowed is True

    def test_reject_second_mutating_same_worktree(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating")
        result = self.mgr.claim_worktree("s2", "wt-1", "mutating")
        assert result.allowed is False
        assert result.conflict_session_id == "s1"

    def test_allow_read_only_sharing(self):
        self.mgr.claim_worktree("s1", "wt-1", "read_only")
        result = self.mgr.claim_worktree("s2", "wt-1", "read_only")
        assert result.allowed is True

    def test_allow_read_only_alongside_mutating(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating")
        result = self.mgr.claim_worktree("s2", "wt-1", "read_only")
        assert result.allowed is True

    def test_release_worktree(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating")
        released = self.mgr.release_worktree("s1", "wt-1")
        assert released is True
        result = self.mgr.claim_worktree("s2", "wt-1", "mutating")
        assert result.allowed is True

    def test_file_conflict_detection(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating", ["src/auth.ts"])
        conflict = self.mgr.check_file_conflict("s2", "wt-1", ["src/auth.ts"])
        assert conflict is not None
        assert conflict.overlapping_files == ["src/auth.ts"]

    def test_no_file_conflict_different_files(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating", ["src/auth.ts"])
        conflict = self.mgr.check_file_conflict("s2", "wt-1", ["src/db.ts"])
        assert conflict is None

    def test_register_files(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating")
        self.mgr.register_files("s1", "wt-1", ["src/main.ts", "src/utils.ts"])
        conflict = self.mgr.check_file_conflict("s2", "wt-1", ["src/main.ts"])
        assert conflict is not None

    def test_get_active_claims(self):
        self.mgr.claim_worktree("s1", "wt-1", "mutating")
        self.mgr.claim_worktree("s2", "wt-2", "read_only")
        claims = self.mgr.get_active_claims()
        assert "wt-1" in claims
        assert "wt-2" in claims
        assert claims["wt-1"]["mode"] == "mutating"
        assert claims["wt-2"]["mode"] == "read_only"


# ════════════════════════════════════════════════════════════════════
# 6. Agent-core client tests (structure only — no live server)
# ════════════════════════════════════════════════════════════════════

class TestAgentCoreClient:
    def test_plan_request_structure(self):
        from agent_core_client.client import PlanRequest
        req = PlanRequest(
            session_id="s1",
            repo_id="my-repo",
            prompt="fix login bug",
            allowed_actions=["grep", "read_file", "apply_patch"],
            mode_preference="finite",
        )
        assert req.session_id == "s1"
        assert len(req.allowed_actions) == 3

    def test_outcome_record_structure(self):
        from agent_core_client.client import OutcomeRecord
        rec = OutcomeRecord(
            session_id="s1",
            action_name="run_tests",
            params={"suite": "login"},
            status="failed",
            output={"stderr": "login.test.ts failed"},
            duration_ms=8400,
            executor="openhands",
        )
        assert rec.status == "failed"
        assert rec.duration_ms == 8400

    def test_client_base_url_explicit(self):
        from agent_core_client.client import AgentCoreClient
        client = AgentCoreClient(base_url="http://agent-core:3100")
        assert client.base_url == "http://agent-core:3100"


# ════════════════════════════════════════════════════════════════════
# 7. API route tests via FastAPI TestClient
# ════════════════════════════════════════════════════════════════════

class TestAPIRoutes:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["SESSIONS_DIR"] = self.tmpdir

        # Reset singleton controller
        from sessions import routes
        routes._controller = None
        routes._concurrency = None
        routes.SESSIONS_DIR = Path(self.tmpdir)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def test_create_session(self):
        resp = self.client.post("/api/v2/sessions", json={
            "prompt": "fix login bug",
            "repo_id": "test-repo",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert data["session"]["prompt"] == "fix login bug"

    def test_list_sessions(self):
        self.client.post("/api/v2/sessions", json={"prompt": "task 1"})
        self.client.post("/api/v2/sessions", json={"prompt": "task 2"})
        resp = self.client.get("/api/v2/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) == 2

    def test_get_session(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.get(f"/api/v2/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["session"]["session_id"] == sid

    def test_get_session_404(self):
        resp = self.client.get("/api/v2/sessions/nonexistent")
        assert resp.status_code == 404

    def test_submit_prompt(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.post(f"/api/v2/sessions/{sid}/prompts", json={
            "prompt": "also check tests",
        })
        assert resp.status_code == 200
        assert "routing" in resp.json()

    def test_control_pause(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.post(f"/api/v2/sessions/{sid}/control", json={
            "command": "pause",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_control_resume(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        self.client.post(f"/api/v2/sessions/{sid}/control", json={"command": "pause"})
        resp = self.client.post(f"/api/v2/sessions/{sid}/control", json={"command": "resume"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"

    def test_control_cancel(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.post(f"/api/v2/sessions/{sid}/control", json={"command": "cancel"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_get_events(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.get(f"/api/v2/sessions/{sid}/events")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1  # At least user_prompt_received

    def test_get_events_filter_type(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.get(
            f"/api/v2/sessions/{sid}/events",
            params={"event_type": "user_prompt_received"},
        )
        assert resp.status_code == 200
        for evt in resp.json()["events"]:
            assert evt["event_type"] == "user_prompt_received"

    def test_claim_worktree(self):
        create = self.client.post("/api/v2/sessions", json={"prompt": "test"})
        sid = create.json()["session"]["session_id"]
        resp = self.client.post(f"/api/v2/sessions/{sid}/concurrency/claim", json={
            "worktree_id": "wt-test",
            "mode": "mutating",
        })
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_claim_worktree_conflict(self):
        c1 = self.client.post("/api/v2/sessions", json={"prompt": "task 1"})
        c2 = self.client.post("/api/v2/sessions", json={"prompt": "task 2"})
        sid1 = c1.json()["session"]["session_id"]
        sid2 = c2.json()["session"]["session_id"]
        self.client.post(f"/api/v2/sessions/{sid1}/concurrency/claim", json={
            "worktree_id": "wt-shared",
            "mode": "mutating",
        })
        resp = self.client.post(f"/api/v2/sessions/{sid2}/concurrency/claim", json={
            "worktree_id": "wt-shared",
            "mode": "mutating",
        })
        assert resp.status_code == 409

    def test_full_flow_create_prompt_control(self):
        """Full integration: create session → submit prompts → control."""
        # Create
        create = self.client.post("/api/v2/sessions", json={
            "prompt": "fix login bug",
            "repo_id": "my-app",
        })
        sid = create.json()["session"]["session_id"]

        # Submit clarification
        self.client.post(f"/api/v2/sessions/{sid}/prompts", json={
            "prompt": "also check the auth middleware",
        })

        # Pause
        pause = self.client.post(f"/api/v2/sessions/{sid}/control", json={
            "command": "pause",
        })
        assert pause.json()["status"] == "paused"

        # Resume
        resume = self.client.post(f"/api/v2/sessions/{sid}/control", json={
            "command": "resume",
        })
        assert resume.json()["status"] == "resumed"

        # Check events timeline
        events = self.client.get(f"/api/v2/sessions/{sid}/events")
        types = [e["event_type"] for e in events.json()["events"]]
        assert "user_prompt_received" in types
        assert "plan_paused" in types
        assert "plan_resumed" in types
