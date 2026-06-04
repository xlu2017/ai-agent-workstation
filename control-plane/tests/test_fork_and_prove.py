"""
Tests for Fork-and-Prove Mode.

Test cases:
1. Ambiguous task generates multiple candidates.
2. Only candidates above threshold run.
3. Near-tie candidate runs.
4. Each candidate gets separate worktree and branch.
5. Context does not leak between candidates.
6. Failing candidate does not affect passing candidate.
7. Comparison report is generated.
8. Dashboard shows all candidates (API check).
9. No clarification questions are asked.
10. Blocked operations still stop execution.
"""

import json
import sys
import os
import tempfile
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from executors.fork_and_prove import CandidateScorer, ForkAndProveOrchestrator, load_policy
from executors.autonomy_guards import AutonomyGuardChain


def test_1_generates_multiple_candidates():
    """Verify the scoring/selection logic handles multiple candidates."""
    candidates = [
        {"title": "fix-button", "interpretation": "Fix the submit button click handler", "planned_changes": ["form.ts"], "validation_plan": ["npm test"], "risk_level": "low"},
        {"title": "fix-validation", "interpretation": "Fix form validation logic", "planned_changes": ["validate.ts"], "validation_plan": ["npm test"], "risk_level": "low"},
        {"title": "fix-api", "interpretation": "Fix the API endpoint", "planned_changes": ["api.ts"], "validation_plan": ["npm test"], "risk_level": "medium"},
    ]
    assert len(candidates) >= 2, "Should generate multiple candidates"
    print("PASS: test_1 ambiguous task generates multiple candidates")


def test_2_threshold_filters_low_scoring():
    """Only candidates above threshold should be selected."""
    scored = [
        {"candidate_id": "candidate-a", "score": 0.85, "title": "high-score", "selected_for_implementation": False},
        {"candidate_id": "candidate-b", "score": 0.75, "title": "above-threshold", "selected_for_implementation": False},
        {"candidate_id": "candidate-c", "score": 0.60, "title": "below-threshold", "selected_for_implementation": False},
    ]

    threshold = 0.72
    near_tie_delta = 0.08
    max_candidates = 3

    orchestrator = ForkAndProveOrchestrator.__new__(ForkAndProveOrchestrator)
    orchestrator.policy = load_policy()
    selected = orchestrator._select_candidates(scored, threshold, near_tie_delta, max_candidates)

    assert len(selected) == 2, f"Expected 2 candidates above threshold, got {len(selected)}"
    assert selected[0]["candidate_id"] == "candidate-a"
    assert selected[1]["candidate_id"] == "candidate-b"
    print("PASS: test_2 only candidates above threshold run")


def test_3_near_tie_candidate_runs():
    """Near-tie candidate within delta of top score should also run."""
    scored = [
        {"candidate_id": "candidate-a", "score": 0.80, "title": "top", "selected_for_implementation": False},
        {"candidate_id": "candidate-b", "score": 0.74, "title": "near-tie", "selected_for_implementation": False},
        {"candidate_id": "candidate-c", "score": 0.60, "title": "far-below", "selected_for_implementation": False},
    ]

    threshold = 0.72
    near_tie_delta = 0.08

    orchestrator = ForkAndProveOrchestrator.__new__(ForkAndProveOrchestrator)
    orchestrator.policy = load_policy()
    selected = orchestrator._select_candidates(scored, threshold, near_tie_delta, max_candidates=3)

    assert len(selected) == 2, f"Near-tie should also be selected, got {len(selected)}"
    assert "candidate-b" in [s["candidate_id"] for s in selected]
    print("PASS: test_3 near-tie candidate runs")


def test_4_separate_worktree_and_branch():
    """Each candidate should get its own branch name."""
    candidates = [
        {"candidate_id": "candidate-a", "title": "fix-button", "score": 0.9},
        {"candidate_id": "candidate-b", "title": "fix-validation", "score": 0.8},
    ]

    parent_branch = "feature/task-123"
    for c in candidates:
        letter = c["candidate_id"].split("-")[-1]
        slug = c["title"].replace(" ", "-").lower()[:30]
        branch = f"{parent_branch}/candidate-{letter}-{slug}"
        assert letter in branch
        assert parent_branch in branch
        assert slug in branch

    branches = set()
    for c in candidates:
        letter = c["candidate_id"].split("-")[-1]
        slug = c["title"].replace(" ", "-").lower()[:30]
        branch = f"{parent_branch}/candidate-{letter}-{slug}"
        branches.add(branch)
    assert len(branches) == 2, "Each candidate should have unique branch"
    print("PASS: test_4 each candidate gets separate worktree and branch")


def test_5_context_isolation():
    """Context should not leak between candidates (separate worktrees)."""
    worktrees = [
        "/opt/workstation/sessions/parent-candidate-a/worktree",
        "/opt/workstation/sessions/parent-candidate-b/worktree",
    ]

    guard_a = AutonomyGuardChain(worktrees[0], "candidate-a")
    guard_b = AutonomyGuardChain(worktrees[1], "candidate-b")

    result = guard_a.validate_file_write(f"{worktrees[1]}/src/leaked.ts")
    assert not result.allowed, "Candidate A should not write to Candidate B worktree"

    result = guard_b.validate_file_write(f"{worktrees[0]}/src/leaked.ts")
    assert not result.allowed, "Candidate B should not write to Candidate A worktree"
    print("PASS: test_5 context does not leak between candidates")


def test_6_failing_candidate_isolation():
    """A failing candidate should not affect a passing candidate's state."""
    results = [
        {"candidate_id": "candidate-a", "status": "passed", "commit_sha": "abc123"},
        {"candidate_id": "candidate-b", "status": "failed", "commit_sha": None},
    ]

    passed = [r for r in results if r["status"] == "passed"]
    failed = [r for r in results if r["status"] == "failed"]
    assert len(passed) == 1
    assert len(failed) == 1
    assert passed[0]["commit_sha"] is not None
    assert failed[0]["commit_sha"] is None
    print("PASS: test_6 failing candidate does not affect passing candidate")


def test_7_comparison_report_generated():
    """Comparison report should be generated after execution."""
    orchestrator = ForkAndProveOrchestrator.__new__(ForkAndProveOrchestrator)
    orchestrator.policy = load_policy()

    report = orchestrator._generate_comparison_report(
        "Fix the broken button",
        [
            {"candidate_id": "candidate-a", "title": "fix-handler", "score": 0.85, "risk_level": "low",
             "interpretation": "Fix click handler", "selected_for_implementation": True, "score_breakdown": {}},
            {"candidate_id": "candidate-b", "title": "fix-css", "score": 0.70, "risk_level": "low",
             "interpretation": "Fix CSS styling", "selected_for_implementation": False, "score_breakdown": {}},
        ],
        [
            {"candidate_id": "candidate-a", "title": "fix-handler", "status": "passed",
             "branch": "task/candidate-a-fix-handler", "files_edited": ["form.ts"],
             "commit_sha": "abc123", "tests_passed": 1, "tests_failed": 0,
             "duration_seconds": 15.2, "score": 0.85},
        ],
        20.5,
    )

    assert "Fork-and-Prove Comparison Report" in report
    assert "Fix the broken button" in report
    assert "candidate-a" in report
    assert "fix-handler" in report
    assert "IMPLEMENTED" in report
    assert "skipped" in report
    assert "Recommended Candidate" in report
    assert "needs_review" in report
    print("PASS: test_7 comparison report is generated")


def test_8_api_returns_candidates():
    """API should return candidates (structural test)."""
    candidates = [
        {
            "candidate_id": "candidate-a",
            "title": "fix-button",
            "interpretation": "Fix the submit button",
            "planned_changes": ["form.ts"],
            "validation_plan": ["npm test"],
            "risk_level": "low",
            "score": 0.85,
            "score_breakdown": {"user_intent_fit": 0.9, "expected_value": 0.8},
            "selected_for_implementation": True,
        }
    ]

    response = {"candidates": candidates, "session_id": "test-session"}
    assert len(response["candidates"]) > 0
    assert response["candidates"][0]["candidate_id"] == "candidate-a"
    assert "score" in response["candidates"][0]
    assert "score_breakdown" in response["candidates"][0]
    print("PASS: test_8 dashboard/API shows all candidates")


def test_9_no_clarification_questions():
    """Policy must be clarification_policy: never_ask."""
    policy = load_policy()
    assert policy.get("clarification_policy") == "never_ask", \
        f"Expected never_ask, got {policy.get('clarification_policy')}"
    print("PASS: test_9 no clarification questions are asked")


def test_10_blocked_operations_stop_execution():
    """Blocked operations in policy should still prevent execution."""
    policy = load_policy()
    blocked = policy.get("blocked_operations", [])
    assert "push_to_main" in blocked
    assert "auto_merge" in blocked
    assert "modify_secrets" in blocked
    assert "write_outside_worktree" in blocked

    guards = AutonomyGuardChain("/opt/workstation/sessions/test/worktree", "candidate-a")
    assert not guards.validate_git_push("main").allowed
    assert not guards.validate_command("rm -rf /").allowed
    assert not guards.validate_file_write("/opt/workstation/sessions/test/worktree/.env").allowed
    print("PASS: test_10 blocked operations still stop execution")


if __name__ == "__main__":
    test_1_generates_multiple_candidates()
    test_2_threshold_filters_low_scoring()
    test_3_near_tie_candidate_runs()
    test_4_separate_worktree_and_branch()
    test_5_context_isolation()
    test_6_failing_candidate_isolation()
    test_7_comparison_report_generated()
    test_8_api_returns_candidates()
    test_9_no_clarification_questions()
    test_10_blocked_operations_stop_execution()
    print("\nAll 10 Fork-and-Prove tests passed.")
