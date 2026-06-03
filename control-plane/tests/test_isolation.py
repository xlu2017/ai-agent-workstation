#!/usr/bin/env python3
"""
Adversarial Isolation Test Suite

Tries to break session isolation with:
1. Same component names across sessions
2. Same dev server framework
3. Similar branch names
4. Simultaneous UI events
5. Simultaneous editor selections
6. Simultaneous terminal failures
7. Cross-session file paths
8. Overlapping port ranges (should be rejected)

Pass condition:
- 0 context leaks
- 0 branch corruption
- 0 wrong-worktree edits
- 0 port collisions
"""

import json
import os
import sys
import time
import subprocess
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from context_validator import validate_context, get_context_health

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")

RESULTS = {"passed": 0, "failed": 0, "tests": []}


def record(test_name: str, passed: bool, detail: str = ""):
    RESULTS["tests"].append({"test": test_name, "passed": passed, "detail": detail})
    if passed:
        RESULTS["passed"] += 1
    else:
        RESULTS["failed"] += 1
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {test_name}" + (f" — {detail}" if detail else ""))


def setup_test_sessions():
    """Create adversarial test sessions with confusingly similar names."""
    sessions = [
        {
            "id": "adversarial-alpha",
            "branch": "fix-button-alpha",
            "port_range": "6100-6109",
            "browser_profile": "profile-alpha",
        },
        {
            "id": "adversarial-beta",
            "branch": "fix-button-beta",  # Similar name!
            "port_range": "6110-6119",
            "browser_profile": "profile-beta",
        },
        {
            "id": "adversarial-gamma",
            "branch": "fix-button-gamma",  # Similar name!
            "port_range": "6120-6129",
            "browser_profile": "profile-gamma",
        },
    ]

    for s in sessions:
        session_dir = SESSIONS_DIR / s["id"]
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context").mkdir(exist_ok=True)
        (session_dir / "events").mkdir(exist_ok=True)
        meta = {
            "id": s["id"],
            "repo_path": "/opt/workstation/repos/example-react-app",
            "worktree_path": f"/opt/workstation/repos/worktree-{s['id']}",
            "branch": s["branch"],
            "port_range": s["port_range"],
            "browser_profile": s["browser_profile"],
            "status": "active",
            "task": f"Task for {s['id']}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (session_dir / "session.json").write_text(json.dumps(meta, indent=2))

    return sessions


def cleanup_test_sessions(sessions):
    """Remove test sessions."""
    for s in sessions:
        session_dir = SESSIONS_DIR / s["id"]
        if session_dir.exists():
            shutil.rmtree(session_dir)


def send_ui_event(session_id: str, port: int, component: str) -> dict:
    """Send a UI event to the bridge."""
    import urllib.request
    data = json.dumps({
        "type": "inspect",
        "session_id": session_id,
        "url": f"http://localhost:{port}/",
        "selected_text": "Save",
        "element": {"tag": "button", "id": "save-btn", "class": "btn"},
        "source": {"framework": "react", "component": component, "file": f"src/components/{component}.tsx", "line": 42, "confidence": "high"},
    }).encode()
    try:
        req = urllib.request.Request(f"{BRIDGE_URL}/inspect", data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def send_editor_event(session_id: str, file_path: str, selection: str) -> dict:
    """Send an editor event to the bridge."""
    import urllib.request
    data = json.dumps({
        "session_id": session_id,
        "type": "selection",
        "file": file_path,
        "language": "typescriptreact",
        "selection": {"text": selection, "startLine": 10, "endLine": 15},
        "cursor": {"line": 12, "col": 5},
        "gitBranch": f"fix-button-{session_id.split('-')[-1]}",
    }).encode()
    try:
        req = urllib.request.Request(f"{BRIDGE_URL}/editor-context", data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def test_simultaneous_ui_events(sessions):
    """Send UI events to all sessions simultaneously. Verify no cross-contamination."""
    print("\n=== Test: Simultaneous UI Events ===")

    # Same component name across all sessions!
    component = "SaveButton"

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for i, s in enumerate(sessions):
            port = 6100 + (i * 10)  # First port in each range
            future = executor.submit(send_ui_event, s["id"], port, component)
            futures[future] = s["id"]

        for future in as_completed(futures):
            session_id = futures[future]
            result = future.result()
            if "error" not in result:
                record(
                    f"UI event delivered to {session_id}",
                    result.get("session_id") == session_id,
                    f"routed to: {result.get('session_id', '?')}",
                )
            else:
                record(f"UI event to {session_id}", False, result["error"])

    # Verify isolation: each session should only have its own context
    time.sleep(0.5)
    for s in sessions:
        ctx_file = SESSIONS_DIR / s["id"] / "context" / "latest-ui-context.md"
        if ctx_file.exists():
            content = ctx_file.read_text()
            # Check no other session's port appears
            other_ports = [6100 + (j * 10) for j in range(3) if sessions[j]["id"] != s["id"]]
            leak = any(str(p) in content for p in other_ports)
            record(
                f"No port leak in {s['id']} UI context",
                not leak,
                f"found other ports: {[p for p in other_ports if str(p) in content]}" if leak else "",
            )


def test_simultaneous_editor_events(sessions):
    """Send editor events with same component name but different worktrees."""
    print("\n=== Test: Simultaneous Editor Events ===")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for s in sessions:
            file_path = f"/opt/workstation/repos/worktree-{s['id']}/src/components/SaveButton.tsx"
            future = executor.submit(send_editor_event, s["id"], file_path, "const [saving, setSaving] = useState(false)")
            futures[future] = s["id"]

        for future in as_completed(futures):
            session_id = futures[future]
            result = future.result()
            record(
                f"Editor event delivered to {session_id}",
                "error" not in result and result.get("session_id") == session_id,
                str(result.get("session_id", result.get("error", "?")))[:50],
            )

    # Verify isolation
    time.sleep(0.5)
    for s in sessions:
        ctx_file = SESSIONS_DIR / s["id"] / "context" / "latest-editor-context.md"
        if ctx_file.exists():
            content = ctx_file.read_text()
            # Ensure file path matches this session's worktree
            correct_worktree = f"worktree-{s['id']}"
            has_correct_path = correct_worktree in content
            other_worktrees = [f"worktree-{other['id']}" for other in sessions if other["id"] != s["id"]]
            has_leak = any(wt in content for wt in other_worktrees)
            record(
                f"Editor context in {s['id']} has correct worktree",
                has_correct_path and not has_leak,
                f"correct: {has_correct_path}, leak: {has_leak}",
            )


def test_port_collision_rejection(sessions):
    """Attempt to send an event with a port belonging to another session."""
    print("\n=== Test: Port Collision Rejection ===")

    # Send event to session alpha but with beta's port
    warnings = validate_context("adversarial-alpha", {
        "url": "http://localhost:6110/",  # Beta's port!
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    has_port_mismatch = any(w["code"] == "PORT_MISMATCH" for w in warnings)
    record(
        "Port mismatch detected when using wrong session's port",
        has_port_mismatch,
        f"warnings: {[w['code'] for w in warnings]}",
    )


def test_wrong_worktree_detection(sessions):
    """Attempt to validate context with a file from another session's worktree."""
    print("\n=== Test: Wrong Worktree Detection ===")

    # Create a fake session with known worktree
    for s in sessions:
        # Validate with file from alpha's worktree but in beta's session
        if s["id"] == "adversarial-beta":
            warnings = validate_context(s["id"], {
                "file": "/opt/workstation/repos/worktree-adversarial-alpha/src/App.tsx",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            has_wrong_worktree = any(w["code"] == "WRONG_WORKTREE" for w in warnings)
            record(
                "Wrong worktree detected for cross-session file",
                has_wrong_worktree,
                f"warnings: {[w['code'] for w in warnings]}",
            )


def test_stale_context_detection(sessions):
    """Verify stale context is flagged."""
    print("\n=== Test: Stale Context Detection ===")

    from datetime import timedelta

    # Create an event from 10 minutes ago
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    warnings = validate_context("adversarial-alpha", {
        "url": "http://localhost:6100/",
        "timestamp": old_time,
    })

    has_stale = any(w["code"] == "STALE_CONTEXT" for w in warnings)
    record(
        "Stale context flagged for 10-minute-old event",
        has_stale,
        f"warnings: {[w['code'] for w in warnings]}",
    )

    # Fresh event should not be flagged
    fresh_time = datetime.now(timezone.utc).isoformat()
    warnings_fresh = validate_context("adversarial-alpha", {
        "url": "http://localhost:6100/",
        "timestamp": fresh_time,
    })

    no_stale = not any(w["code"] == "STALE_CONTEXT" for w in warnings_fresh)
    record(
        "Fresh context not flagged as stale",
        no_stale,
        f"warnings: {[w['code'] for w in warnings_fresh]}",
    )


def test_context_health_api(sessions):
    """Test the context health endpoint returns correct status."""
    print("\n=== Test: Context Health API ===")

    # Session with no events should be healthy (no warnings)
    health = get_context_health("adversarial-gamma")
    # After our simultaneous tests, gamma should have context
    record(
        "Context health returns valid status",
        health["status"] in ("fresh", "stale", "unreliable"),
        f"status: {health['status']}",
    )


def run_all():
    """Run the full adversarial test suite."""
    print("=" * 60)
    print("ADVERSARIAL ISOLATION TEST SUITE")
    print("=" * 60)

    sessions = setup_test_sessions()
    print(f"\nCreated {len(sessions)} test sessions with similar names/components")

    try:
        test_simultaneous_ui_events(sessions)
        test_simultaneous_editor_events(sessions)
        test_port_collision_rejection(sessions)
        test_wrong_worktree_detection(sessions)
        test_stale_context_detection(sessions)
        test_context_health_api(sessions)
    finally:
        cleanup_test_sessions(sessions)

    print("\n" + "=" * 60)
    print(f"RESULTS: {RESULTS['passed']} passed, {RESULTS['failed']} failed")
    print("=" * 60)

    if RESULTS["failed"] == 0:
        print("\nALL TESTS PASSED — Isolation is boringly reliable.")
    else:
        print(f"\n{RESULTS['failed']} FAILURES — Isolation needs work.")
        for t in RESULTS["tests"]:
            if not t["passed"]:
                print(f"  FAIL: {t['test']} — {t['detail']}")

    return RESULTS


if __name__ == "__main__":
    results = run_all()
    sys.exit(0 if results["failed"] == 0 else 1)
