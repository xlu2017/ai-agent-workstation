"""Small deterministic classifier for graph-session follow-up prompts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GraphPromptRoute(str, Enum):
    CONTINUE_ACTIVE = "continue_active"
    QUESTION_ONLY = "question_only"
    CREATE_CHILD_GOAL = "create_child_goal"
    CREATE_SIBLING_GOAL = "create_sibling_goal"


@dataclass(frozen=True)
class GraphPromptClassification:
    route: GraphPromptRoute
    reason: str


QUESTION_PREFIXES = (
    "why ",
    "what ",
    "how ",
    "where ",
    "when ",
    "who ",
    "is ",
    "are ",
    "can you explain",
    "explain ",
    "reason out",
)

SEPARATE_ROOT_PHRASES = (
    "new session",
    "new root",
    "separate session",
    "different goal",
    "unrelated task",
    "unrelated goal",
    "start over",
)

CHILD_GOAL_PHRASES = (
    "separate task",
    "child task",
    "subtask",
    "also create a task",
    "track this separately",
)

ACTION_WORDS = (
    "continue",
    "implement",
    "fix",
    "add",
    "remove",
    "change",
    "update",
    "refactor",
    "run",
    "test",
    "commit",
    "create",
    "build",
)


def classify_graph_prompt(content: str) -> GraphPromptClassification:
    text = " ".join(content.strip().lower().split())
    if not text:
        return GraphPromptClassification(GraphPromptRoute.QUESTION_ONLY, "empty_prompt")

    if any(phrase in text for phrase in SEPARATE_ROOT_PHRASES):
        return GraphPromptClassification(GraphPromptRoute.CREATE_SIBLING_GOAL, "explicit_separate_goal")

    if any(phrase in text for phrase in CHILD_GOAL_PHRASES):
        return GraphPromptClassification(GraphPromptRoute.CREATE_CHILD_GOAL, "explicit_child_goal")

    starts_as_question = text.endswith("?") or any(text.startswith(prefix) for prefix in QUESTION_PREFIXES)
    has_action_word = any(word in text.split() for word in ACTION_WORDS)
    if starts_as_question and not has_action_word:
        return GraphPromptClassification(GraphPromptRoute.QUESTION_ONLY, "question_without_action")

    return GraphPromptClassification(GraphPromptRoute.CONTINUE_ACTIVE, "continue_existing_goal")
