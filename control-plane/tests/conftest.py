from __future__ import annotations

import pytest

from api.services.session_graph_prompt_recommendation import PromptRouteRecommendation


def _route_from_prompt(prompt: str) -> str:
    text = " ".join(prompt.lower().split())
    if "new session" in text or "different goal" in text:
        return "create_sibling_goal"
    if "child task" in text or "subtask" in text:
        return "create_child_goal"
    if text.endswith("?") and not any(word in text.split() for word in {"continue", "run", "fix", "add", "update", "create"}):
        return "question_only"
    return "continue_active"


@pytest.fixture(autouse=True)
def patch_graph_chat_route_for_unit_tests(request, monkeypatch):
    if getattr(request.module, "__name__", "") != "test_session_graph_chat":
        return

    def fake_route(_session, prompt: str):
        return PromptRouteRecommendation(route=_route_from_prompt(prompt), reason="unit test route", source="unit_test")

    monkeypatch.setattr("api.routes.session_graph.chat.recommend_graph_prompt_route", fake_route)
