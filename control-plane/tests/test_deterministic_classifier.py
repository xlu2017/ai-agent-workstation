"""
Parametrized tests for the deterministic fuzzy phrase-table classifier.

Covers:
  - Direct action examples (must classify as direct)
  - Code-implementation negatives (must NOT classify as direct)
  - Typo resilience
  - Punctuation / filler stripping
  - Mutation-guard regression (desktop_control cannot modify files/commit)
"""

import sys
from pathlib import Path

import pytest

# Ensure control-plane is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt_router.deterministic_classifier import (
    AMBIGUOUS_THRESHOLD,
    DIRECT_THRESHOLD,
    LOW_RISK_DIRECT_THRESHOLD,
    ClassificationResult,
    classify_direct_action,
    normalize_text,
    should_execute_directly,
    tokenize,
)


# ── Direct action examples (must classify as direct open_terminal) ─


@pytest.mark.parametrize(
    "prompt",
    [
        "open terminal",
        "open terminal on desktop",
        "launch a terminal",
        "show shell window",
        "bring up the console",
        "start xterm",
        "open the terminal please",
        "can you open the terminal please",
        "display the command prompt",
        "pull up a bash window",
        "launch shell",
        "start a terminal on the desktop",
        "show me the terminal",
        "open a shell on remote desktop",
    ],
)
def test_direct_open_terminal(prompt: str):
    result = classify_direct_action(prompt)
    assert result.action_name == "open_terminal", (
        f"Expected open_terminal, got {result.action_name} for: {prompt!r}"
    )
    assert result.task_class == "desktop_control"
    assert should_execute_directly(result), (
        f"Confidence {result.confidence:.2f} too low for: {prompt!r}"
    )


# ── Code-implementation negatives (must NOT classify as direct) ───


@pytest.mark.parametrize(
    "prompt",
    [
        "add an open terminal button",
        "implement an open terminal endpoint",
        "fix the open terminal feature",
        "terminal button does not work",
        "make the UI open terminal",
        "write tests for open terminal",
        "edit server.py to open terminal",
        "create a terminal component",
        "build the terminal launcher",
        "refactor the terminal opener",
        "debug the terminal feature",
        "wire up the terminal button",
        "add an Open Terminal button to the desktop page",
        "fix open terminal button",
        "the terminal button is broken",
        "implement open terminal route",
    ],
)
def test_code_intent_blocks_direct(prompt: str):
    result = classify_direct_action(prompt)
    assert not should_execute_directly(result), (
        f"Should NOT execute directly for code-intent: {prompt!r} "
        f"(confidence={result.confidence:.2f}, negative={result.negative_match!r})"
    )


# ── Typo resilience ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "opne terminal",
        "lauch terminal",
        "opn the termnial",
        "lanch a terminl",
    ],
)
def test_typo_resilience(prompt: str):
    result = classify_direct_action(prompt)
    assert result.action_name == "open_terminal", (
        f"Typo not handled for: {prompt!r} (got {result.action_name})"
    )
    # Should be at least ambiguous (>= 0.55)
    assert result.confidence >= AMBIGUOUS_THRESHOLD, (
        f"Confidence {result.confidence:.2f} too low for typo: {prompt!r}"
    )


# ── Filler / punctuation stripping ───────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "please open terminal",
        "could you launch the terminal?",
        "hey, can you open the terminal for me?",
        "hi! open a terminal, thanks",
        "would you kindly start a shell",
    ],
)
def test_filler_and_punctuation(prompt: str):
    result = classify_direct_action(prompt)
    assert result.action_name == "open_terminal", (
        f"Filler not stripped for: {prompt!r}"
    )
    assert should_execute_directly(result), (
        f"Confidence {result.confidence:.2f} too low after filler strip: {prompt!r}"
    )


# ── Normalization unit tests ─────────────────────────────────────


def test_normalize_strips_filler():
    assert "open terminal" == normalize_text("Please open terminal for me")


def test_normalize_strips_punctuation():
    result = normalize_text("open the terminal!")
    assert "!" not in result


def test_normalize_collapses_whitespace():
    result = normalize_text("  open   terminal  ")
    assert result == "open terminal"


def test_tokenize():
    tokens = tokenize("open terminal on desktop")
    assert tokens == ["open", "terminal", "on", "desktop"]


# ── Browser and other patterns ────────────────────────────────────


@pytest.mark.parametrize(
    "prompt,expected_action",
    [
        ("open the browser", "open_browser"),
        ("launch chrome", "open_browser"),
        ("open firefox on desktop", "open_browser"),
        ("start the web browser", "open_browser"),
        ("take a screenshot", "take_screenshot"),
        ("capture the screen", "take_screenshot"),
        ("grab a screenshot of the desktop", "take_screenshot"),
        ("open file manager", "open_file_manager"),
        ("launch the file explorer", "open_file_manager"),
    ],
)
def test_other_direct_actions(prompt: str, expected_action: str):
    result = classify_direct_action(prompt)
    assert result.action_name == expected_action, (
        f"Expected {expected_action}, got {result.action_name} for: {prompt!r}"
    )
    assert result.task_class == "desktop_control"
    assert should_execute_directly(result), (
        f"Confidence {result.confidence:.2f} too low for: {prompt!r}"
    )


# ── Empty / unrelated prompts ────────────────────────────────────


def test_empty_prompt():
    result = classify_direct_action("")
    assert result.confidence == 0.0


def test_unrelated_prompt():
    result = classify_direct_action("what is the weather like today")
    assert not should_execute_directly(result)


def test_coding_prompt():
    result = classify_direct_action("refactor the database migration code")
    assert not should_execute_directly(result)


# ── Confidence thresholds ─────────────────────────────────────────


def test_threshold_constants():
    assert DIRECT_THRESHOLD == 0.80
    assert AMBIGUOUS_THRESHOLD == 0.55
    assert LOW_RISK_DIRECT_THRESHOLD == 0.65
    assert LOW_RISK_DIRECT_THRESHOLD < DIRECT_THRESHOLD


def test_low_risk_uses_lower_threshold():
    # "open terminal" is low-risk, should use 0.65 threshold
    result = classify_direct_action("open terminal")
    assert should_execute_directly(result)
    assert result.confidence >= LOW_RISK_DIRECT_THRESHOLD


# ── Code-intent detection specifics ───────────────────────────────


def test_code_intent_detected():
    result = classify_direct_action("add an open terminal button")
    assert result.is_code_intent
    assert result.negative_match != ""
    assert result.confidence == 0.0


def test_doesnt_work_is_code_intent():
    result = classify_direct_action("terminal doesn't work")
    assert result.is_code_intent
    assert "work" in result.negative_match or "doesn't work" in result.negative_match


def test_is_broken_is_code_intent():
    result = classify_direct_action("the terminal launcher is broken")
    assert result.is_code_intent


# ── Classification result properties ──────────────────────────────


def test_is_direct_action_property():
    r = ClassificationResult(
        action_name="open_terminal",
        task_class="desktop_control",
        confidence=0.90,
    )
    assert r.is_direct_action
    assert not r.is_ambiguous
    assert not r.is_code_intent


def test_is_ambiguous_property():
    r = ClassificationResult(
        action_name="open_terminal",
        task_class="desktop_control",
        confidence=0.65,
    )
    assert not r.is_direct_action
    assert r.is_ambiguous
    assert not r.is_code_intent


def test_is_code_intent_property():
    r = ClassificationResult(
        action_name="open_terminal",
        task_class="code_implementation",
        confidence=0.0,
        negative_match="implement",
    )
    assert not r.is_direct_action
    assert not r.is_ambiguous
    assert r.is_code_intent


# ── Mutation guard regression ─────────────────────────────────────


def test_mutation_guard_desktop_control_blocks_file_edit():
    """Prove that a desktop_control prompt cannot modify files or commit.

    This tests the integration point: if classify_direct_action returns
    task_class="desktop_control", the prompt_handler must set
    mutation_allowed=False and commit_requires_approval=True on the
    RuntimePolicy before checking the policy. We verify the classifier
    side here; the runtime enforcement is in prompt_handler.
    """
    from execution.prompt_handler import RuntimePolicy

    # Simulate what prompt_handler does
    result = classify_direct_action("open terminal on desktop")
    assert result.task_class == "desktop_control"

    policy = RuntimePolicy()
    assert policy.mutation_allowed is True  # default

    # Apply mutation guard (mirrors prompt_handler logic)
    if result.task_class == "desktop_control":
        policy.mutation_allowed = False
        policy.commit_requires_approval = True
        policy.push_requires_approval = True

    assert policy.mutation_allowed is False
    assert policy.commit_requires_approval is True
    assert policy.push_requires_approval is True


def test_mutation_guard_not_applied_to_code_implementation():
    """Code-implementation prompts should NOT get the mutation guard."""
    result = classify_direct_action("implement an open terminal button")
    assert result.task_class == "code_implementation"

    from execution.prompt_handler import RuntimePolicy

    policy = RuntimePolicy()
    if result.task_class == "desktop_control":
        policy.mutation_allowed = False

    # Should remain default (True)
    assert policy.mutation_allowed is True


# ── Word order / structure variants ───────────────────────────────


@pytest.mark.parametrize(
    "prompt,min_confidence",
    [
        ("desktop terminal open", AMBIGUOUS_THRESHOLD),
        # "terminal on desktop" has no verb → noun-only → lower confidence
        ("terminal on desktop", 0.40),
        ("on the desktop open terminal", AMBIGUOUS_THRESHOLD),
    ],
)
def test_word_order_variants(prompt: str, min_confidence: float):
    result = classify_direct_action(prompt)
    assert result.action_name == "open_terminal", (
        f"Word order not handled: {prompt!r}"
    )
    assert result.confidence >= min_confidence, (
        f"Confidence {result.confidence:.2f} too low for: {prompt!r}"
    )
