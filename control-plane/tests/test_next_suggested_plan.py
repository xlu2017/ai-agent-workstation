import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_next_suggestion_to_plan_wraps_one_action():
    from execution.next_suggested_plan import next_suggestion_to_plan

    plan = next_suggestion_to_plan(
        prompt="fix selected button",
        recommendation={
            "ok": True,
            "next_action": {
                "action_name": "read_file",
                "params": {"path": "src/components/SaveButton.tsx"},
                "rationale": "Inspect the selected component first.",
            },
        },
    )

    assert plan["source"] == "next_suggested_plan"
    assert plan["advisory_only"] is True
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["action_name"] == "read_file"
    assert plan["steps"][0]["params"] == {"path": "src/components/SaveButton.tsx"}


def test_next_suggestion_to_plan_rejects_plan_shaped_payload():
    from execution.next_suggested_plan import NextSuggestedPlanError, next_suggestion_to_plan

    try:
        next_suggestion_to_plan(
            prompt="fix selected button",
            recommendation={"ok": True, "plan": {"steps": [{"action_name": "read_file"}]}},
        )
    except NextSuggestedPlanError as exc:
        assert "must suggest exactly one action" in str(exc)
    else:
        raise AssertionError("expected NextSuggestedPlanError")


def test_next_suggestion_to_plan_accepts_string_action():
    from execution.next_suggested_plan import next_suggestion_to_plan

    plan = next_suggestion_to_plan(
        prompt="run tests",
        recommendation={"ok": True, "next_action": "run_tests"},
    )

    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["action_name"] == "run_tests"
    assert plan["steps"][0]["params"] == {}
