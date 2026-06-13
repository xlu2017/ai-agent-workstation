from __future__ import annotations

import pytest

from api.services.session_graph_prompt_recommendation import _parse_recommendation
from execution.next_suggested_plan import NextSuggestedStop, next_suggestion_to_plan


def test_next_suggested_plan_accepts_next_task_decision_payload() -> None:
    plan = next_suggestion_to_plan(
        prompt="Find TODOs",
        recommendation={
            "next_task_decision": {
                "decision": "execute",
                "task_name": "grep",
                "params": {"pattern": "TODO"},
                "certainty": 0.8,
                "stakes": "read_only",
                "risk": "low",
                "reason": "Search first.",
                "missing_information": [],
                "expected_result": "Search results are available.",
                "success_criteria": ["A result is returned."],
                "forbidden_actions": [],
            }
        },
    )

    assert plan["steps"] == [
        {
            "action_name": "grep",
            "params": {"pattern": "TODO"},
            "rationale": "Search first.",
            "source": "next_suggested_plan",
        }
    ]


def test_next_suggested_plan_treats_stop_as_terminal() -> None:
    with pytest.raises(NextSuggestedStop) as exc:
        next_suggestion_to_plan(
            prompt="Done",
            recommendation={
                "next_task_decision": {
                    "decision": "stop",
                    "task_name": "stop",
                    "params": {},
                    "certainty": 0.9,
                    "stakes": "read_only",
                    "risk": "low",
                    "reason": "Finished.",
                    "missing_information": [],
                    "expected_result": "No action is emitted.",
                    "success_criteria": ["No step exists."],
                    "forbidden_actions": [],
                }
            },
        )

    assert "Finished" in str(exc.value)


def test_graph_prompt_router_accepts_next_task_decision_payload() -> None:
    parsed = _parse_recommendation(
        {
            "source": "llm_next_task_decision",
            "next_task_decision": {
                "decision": "execute",
                "task_name": "session.route_prompt",
                "params": {
                    "route": "create_child_goal",
                    "target_session_id": "s1",
                    "prompt": "Make this a subtask",
                    "reason": "The user requested a subtask.",
                },
                "certainty": 0.8,
                "stakes": "read_only",
                "risk": "low",
                "reason": "Route the follow-up.",
                "missing_information": [],
                "expected_result": "The prompt is routed.",
                "success_criteria": ["A route is selected."],
                "forbidden_actions": [],
            },
        }
    )

    assert parsed is not None
    assert parsed.route == "create_child_goal"
    assert parsed.reason == "The user requested a subtask."
    assert parsed.source == "llm_next_task_decision"
