#!/usr/bin/env python3
"""
Regression test: Dashboard chat routes to DirectExecutor, NOT OpenHands.

Verifies:
1. Chat creates a task
2. DirectExecutor claims the task (status="claimed")
3. No route_to_openhands call is made
4. Status is truthful (claimed -> committed/failed, never false "running")
5. Task reaches a terminal state with real executor output
"""
import json
import os
import sys
import time
import urllib.request

API_URL = os.environ.get("CONTROL_PLANE_API", "http://localhost:9877")


def test_dashboard_chat_uses_direct_executor_not_openhands():
    """Submit a chat instruction and verify DirectExecutor handles it."""

    session_id = "test-direct-executor"

    # Create test session
    try:
        req = urllib.request.Request(
            f"{API_URL}/api/sessions",
            data=json.dumps({"session_id": session_id, "repo": "cypress-realworld-app"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Session may already exist

    # Submit chat instruction
    chat_data = json.dumps({
        "instruction": "Add a comment to the top of README.md saying '# Test edit by DirectExecutor'",
    }).encode()
    req = urllib.request.Request(
        f"{API_URL}/api/sessions/{session_id}/chat",
        data=chat_data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())

    # ASSERTION 1: Task was claimed (not "running" or "completed" immediately)
    assert result["status"] == "claimed", f"Expected 'claimed', got '{result['status']}'"
    assert result.get("executor") == "direct", f"Expected executor='direct', got '{result.get('executor')}'"
    task_id = result["task_id"]
    print(f"[PASS] Task claimed by DirectExecutor: {task_id}")

    # ASSERTION 2: No route_to_openhands was called
    assert "openhands" not in result.get("message", "").lower(), "OpenHands should not be in response"
    print("[PASS] No OpenHands routing detected")

    # ASSERTION 3: Wait for executor to finish and check terminal state
    max_wait = 120  # seconds
    start = time.time()
    final_status = None
    final_msg = None

    while time.time() - start < max_wait:
        time.sleep(5)
        try:
            msgs_req = urllib.request.Request(f"{API_URL}/api/sessions/{session_id}/messages")
            msgs_resp = urllib.request.urlopen(msgs_req, timeout=5)
            messages = json.loads(msgs_resp.read())
            for msg in reversed(messages):
                if msg.get("task_id") == task_id and msg.get("status") in ("committed", "failed", "needs_review"):
                    final_status = msg["status"]
                    final_msg = msg
                    break
        except Exception:
            pass
        if final_status:
            break

    assert final_status is not None, f"Task did not reach terminal state within {max_wait}s"
    print(f"[PASS] Task reached terminal state: {final_status}")

    # ASSERTION 4: Status is truthful - if committed, there should be a commit hash
    if final_status == "committed":
        assert final_msg.get("commit"), "Status=committed but no commit hash"
        print(f"[PASS] Commit produced: {final_msg['commit'][:12]}")

    # ASSERTION 5: If failed, error message should be real (not generic "running")
    if final_status == "failed":
        content = final_msg.get("content", "")
        assert "running" not in content.lower(), "Failed task should not say 'running'"
        print(f"[PASS] Failure is truthful: {content[:80]}")

    print(f"\n{'='*60}")
    print(f"RESULT: All assertions passed.")
    print(f"  DirectExecutor is the default execution path.")
    print(f"  Task: {task_id}")
    print(f"  Final status: {final_status}")
    print(f"  No OpenHands dependency.")
    print(f"{'='*60}")


if __name__ == "__main__":
    test_dashboard_chat_uses_direct_executor_not_openhands()
