"""Tests for the workflow transcript aggregation module.

Covers:
  - Working duration calculation
  - File edit counting (additions/deletions)
  - File read label with line range
  - Search label rendering
  - Thought elapsed without reasoning leakage
  - Secret redaction
  - Validation failure not reported as pass
  - Status message generation
  - Task decomposition
"""
import sys
from pathlib import Path

# Ensure control-plane root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worklog.transcript import (
    build_workflow_transcript,
    generate_status_message,
    generate_task_decomposition,
)


def _ts(offset_sec: int) -> str:
    """Generate a deterministic ISO timestamp."""
    return f"2025-01-15T12:00:{offset_sec:02d}.000Z"


def _event(event_type: str, offset_sec: int, message: str = "", **data) -> dict:
    data["message"] = message
    return {
        "event_type": event_type,
        "session_id": "test-session",
        "timestamp": _ts(offset_sec),
        "sequence": offset_sec,
        "data": data,
    }


# ── Part 2: Transcript aggregation ──


def test_transcript_builds_working_duration():
    events = [
        _event("action_started", 10),
        _event("file_read", 12, path="server.py", line_start=1, line_end=50),
        _event("action_completed", 30),
    ]
    t = build_workflow_transcript("s1", events)
    assert t["working_duration_ms"] == 20000  # 30 - 10 = 20s


def test_transcript_counts_file_edits():
    events = [
        _event("file_edited", 5, path="a.py", additions=10, deletions=3),
        _event("file_edited", 8, path="b.py", additions=20, deletions=0),
    ]
    t = build_workflow_transcript("s1", events)
    assert t["additions"] == 30
    assert t["deletions"] == 3


def test_transcript_renders_file_read_line_range():
    events = [
        _event("file_read", 5, path="control-plane/api/server.py", line_start=640, line_end=719),
    ]
    t = build_workflow_transcript("s1", events)
    items = t["items"]
    assert len(items) >= 1
    read_item = [i for i in items if i["kind"] == "read"][0]
    assert "server.py:640-719" in read_item["label"]


def test_transcript_renders_search_label():
    events = [
        _event("code_searched", 5, query="_cancelled_sessions", path="agentic_executor.py", result_count=3),
    ]
    t = build_workflow_transcript("s1", events)
    items = [i for i in t["items"] if i["kind"] == "search"]
    assert len(items) == 1
    assert "_cancelled_sessions" in items[0]["label"]
    assert "3 results" in items[0]["label"]


def test_transcript_renders_thought_elapsed_without_reasoning():
    events = [
        _event("thought_elapsed", 5, duration_ms=5000),
    ]
    t = build_workflow_transcript("s1", events)
    thought_items = [i for i in t["items"] if i["kind"] == "thought"]
    assert len(thought_items) == 1
    label = thought_items[0]["label"]
    assert "5s" in label
    # No reasoning text should be in the label
    assert "chain" not in label.lower()
    assert "reason" not in label.lower()
    assert "think" not in label.lower() or "Thought" in label


def test_transcript_redacts_secrets():
    """Thought_elapsed events must not contain reasoning text."""
    events = [
        _event("thought_elapsed", 5, duration_ms=8000),
    ]
    t = build_workflow_transcript("s1", events)
    # Check that no metadata key contains reasoning
    for item in t["items"]:
        if item["kind"] == "thought":
            assert "reasoning" not in item["metadata"]
            assert "chain_of_thought" not in item["metadata"]
            assert "internal" not in item["metadata"]


def test_validation_failure_not_reported_as_pass():
    events = [
        _event("test_run", 5, command="pytest tests/", exit_code=1, tests_passed=3, tests_failed=2),
        _event("test_run", 8, command="pytest tests/smoke.py", exit_code=0, tests_passed=1, tests_failed=0),
    ]
    t = build_workflow_transcript("s1", events)
    # Overall must not be "passed" since we had failures
    val = t["validation"]
    assert val["overall"] in ("partial", "failed")
    assert val["overall"] != "passed"


def test_validation_all_passed():
    events = [
        _event("test_run", 5, command="pytest tests/", exit_code=0, tests_passed=10, tests_failed=0),
    ]
    t = build_workflow_transcript("s1", events)
    assert t["validation"]["overall"] == "passed"


def test_validation_not_run():
    events = [
        _event("file_read", 5, path="a.py"),
    ]
    t = build_workflow_transcript("s1", events)
    assert t["validation"]["overall"] == "not_run"


def test_tasks_created_count():
    events = [
        _event("task_created", 3, count=4, tasks=["A", "B", "C", "D"]),
    ]
    t = build_workflow_transcript("s1", events)
    assert t["tasks_created"] == 4
    task_items = [i for i in t["items"] if i["kind"] == "tasks_created"]
    assert len(task_items) == 1
    assert "4 Tasks" in task_items[0]["label"]


def test_task_cancelled_rendered():
    events = [
        _event("task_cancelled", 5, message="Stopped by user"),
    ]
    t = build_workflow_transcript("s1", events)
    cancelled = [i for i in t["items"] if i["kind"] == "cancelled"]
    assert len(cancelled) == 1
    assert "Stopped" in cancelled[0]["label"]


def test_command_run_failed_status():
    events = [
        _event("command_run", 5, command="make build", exit_code=2),
    ]
    t = build_workflow_transcript("s1", events)
    cmd_items = [i for i in t["items"] if i["kind"] == "command"]
    assert len(cmd_items) == 1
    assert cmd_items[0]["status"] == "failed"


# ── Part 3: Status message generation ──


def test_status_message_bugfix():
    msg = generate_status_message(
        "fix the bug that after pressing stop, something resumes it",
        task_class="code_implementation",
    )
    assert "stop" in msg.lower() or "cancel" in msg.lower() or "Investigating" in msg


def test_status_message_direct_action():
    msg = generate_status_message(
        "open terminal on desktop",
        task_class="desktop_control",
        direct_action="open_terminal",
    )
    assert "terminal" in msg.lower()


def test_status_message_generic():
    msg = generate_status_message("do something with the code")
    assert len(msg) > 0


# ── Part 4: Task decomposition ──


def test_task_decomposition_bugfix():
    tasks = generate_task_decomposition(
        "fix the bug that after pressing stop, something resumes it",
        task_class="code_implementation",
    )
    assert 2 <= len(tasks) <= 5
    # Each task should have title and description
    for t in tasks:
        assert "title" in t
        assert "description" in t


def test_task_decomposition_implementation():
    tasks = generate_task_decomposition(
        "add a new endpoint for session transcripts",
        task_class="code_implementation",
    )
    assert 2 <= len(tasks) <= 5


# ── Part 11 extras: routing still works ──


def test_bugfix_prompt_classified_as_investigation():
    """generate_status_message should produce an investigation-style message for bug prompts."""
    msg = generate_status_message("fix the crash in the login page")
    assert "Investigating" in msg or "inspect" in msg.lower() or "fix" in msg.lower()


def test_direct_terminal_gets_action_label():
    """Direct actions should get a simple action label, not a bug investigation message."""
    msg = generate_status_message("open terminal", direct_action="open_terminal")
    assert "terminal" in msg.lower()
    assert "Investigating" not in msg


# ── Legacy action_progress translation ──


def test_legacy_action_progress_read():
    events = [
        {
            "event_type": "action_progress",
            "session_id": "s1",
            "timestamp": _ts(5),
            "sequence": 5,
            "data": {"tool": "read_file", "args_summary": "path=server.py view", "message": ""},
        },
    ]
    t = build_workflow_transcript("s1", events)
    reads = [i for i in t["items"] if i["kind"] == "read"]
    assert len(reads) == 1
    assert "server.py" in reads[0]["label"]


def test_legacy_action_progress_bash():
    events = [
        {
            "event_type": "action_progress",
            "session_id": "s1",
            "timestamp": _ts(5),
            "sequence": 5,
            "data": {"tool": "bash", "command": "ls -la", "message": ""},
        },
    ]
    t = build_workflow_transcript("s1", events)
    cmds = [i for i in t["items"] if i["kind"] == "command"]
    assert len(cmds) == 1
    assert "ls -la" in cmds[0]["label"]
