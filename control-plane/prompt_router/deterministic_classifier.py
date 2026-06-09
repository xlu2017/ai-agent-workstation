"""
Deterministic fuzzy phrase-table classifier for direct platform actions.

Runs BEFORE the LLM router as a fast path.  Classifies prompts like
"open terminal on desktop" into direct_platform_action routes without
needing an LLM call.

Design (layered matcher):
  1. Normalize text (case, punctuation, whitespace, filler)
  2. Detect negation / code-implementation intent
  3. Detect domain nouns
  4. Detect intent verbs
  5. Score candidate routes
  6. Apply confidence threshold
  7. If ambiguous, caller falls back to LLM or planner

Uses only stdlib (difflib.SequenceMatcher) for fuzzy matching.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


# ── Data types ────────────────────────────────────────────────────


@dataclass
class DirectActionPattern:
    """A pattern describing a single direct platform action."""

    action_name: str
    task_class: str
    positive_verbs: set[str]
    positive_nouns: set[str]
    context_terms: set[str] = field(default_factory=set)
    negative_code_terms: set[str] = field(default_factory=set)
    low_risk: bool = False


@dataclass
class ClassificationResult:
    """Result of classifying a prompt against the pattern table."""

    action_name: str       # e.g. "open_terminal", "" if no match
    task_class: str        # e.g. "desktop_control", "code_implementation", ""
    confidence: float      # 0.0 – 1.0
    matched_verb: str = ""
    matched_noun: str = ""
    matched_context: str = ""
    negative_match: str = ""

    @property
    def is_direct_action(self) -> bool:
        return self.confidence >= DIRECT_THRESHOLD and self.action_name != ""

    @property
    def is_ambiguous(self) -> bool:
        return AMBIGUOUS_THRESHOLD <= self.confidence < DIRECT_THRESHOLD and self.action_name != ""

    @property
    def is_code_intent(self) -> bool:
        return self.negative_match != ""


# ── Confidence thresholds ─────────────────────────────────────────

DIRECT_THRESHOLD = 0.80
AMBIGUOUS_THRESHOLD = 0.55
LOW_RISK_DIRECT_THRESHOLD = 0.65


# ── Shared negative / code-intent terms ───────────────────────────

CODE_INTENT_TERMS: set[str] = {
    "add", "implement", "build", "create", "code", "modify", "edit",
    "fix", "refactor", "wire", "endpoint", "button", "api", "ui",
    "component", "route", "test", "write", "debug",
}

CODE_INTENT_PHRASES: list[str] = [
    "wire up",
    "set up",
    "hook up",
    "plug in",
    "does not work",
    "doesn't work",
    "doesnt work",
    "is broken",
    "is not working",
    "isn't working",
    "isnt working",
    "not working",
    "write tests",
    "add tests",
]


# ── Pattern table ─────────────────────────────────────────────────

DIRECT_ACTION_PATTERNS: list[DirectActionPattern] = [
    DirectActionPattern(
        action_name="open_terminal",
        task_class="desktop_control",
        positive_verbs={
            "open", "launch", "start", "show", "display",
            "bring up", "pull up", "focus", "switch to",
        },
        positive_nouns={
            "terminal", "shell", "console", "command prompt",
            "xterm", "xfce terminal", "bash window", "bash",
            "command line", "cli",
        },
        context_terms={
            "desktop", "remote desktop", "screen", "window", "gui",
        },
        negative_code_terms=CODE_INTENT_TERMS,
        low_risk=True,
    ),
    DirectActionPattern(
        action_name="open_browser",
        task_class="desktop_control",
        positive_verbs={
            "open", "launch", "start", "show", "display",
            "bring up", "pull up", "navigate to", "go to",
            "browse", "visit",
        },
        positive_nouns={
            "browser", "chrome", "firefox", "web browser",
            "chromium", "web page", "webpage", "website",
        },
        context_terms={
            "desktop", "remote desktop", "screen", "window", "gui",
            "url", "http", "https",
        },
        negative_code_terms=CODE_INTENT_TERMS,
        low_risk=True,
    ),
    DirectActionPattern(
        action_name="open_file_manager",
        task_class="desktop_control",
        positive_verbs={
            "open", "launch", "start", "show", "display",
            "bring up", "pull up",
        },
        positive_nouns={
            "file manager", "files", "file explorer", "nautilus",
            "thunar", "file browser",
        },
        context_terms={
            "desktop", "remote desktop", "screen", "window", "gui",
        },
        negative_code_terms=CODE_INTENT_TERMS,
        low_risk=True,
    ),
    DirectActionPattern(
        action_name="take_screenshot",
        task_class="desktop_control",
        positive_verbs={
            "take", "capture", "grab", "screenshot", "snap",
            "get", "save",
        },
        positive_nouns={
            "screenshot", "screen capture", "screen shot",
            "screen grab", "screencap", "snapshot", "screen",
        },
        context_terms={
            "desktop", "remote desktop", "screen", "window",
        },
        negative_code_terms=CODE_INTENT_TERMS,
        low_risk=True,
    ),
]


# ── Normalization ─────────────────────────────────────────────────

_FILLER_RE = re.compile(
    r"\b(?:"
    r"please|pls|plz|kindly|"
    r"would you|could you|can you|will you|do you mind|"
    r"for me|for us|right now|asap|quickly|"
    r"just|maybe|perhaps|actually|basically|simply|"
    r"i want to|i need to|id like to|i would like to|"
    r"lets|let me|go ahead and|"
    r"hey|hi|hello|thanks|thank you|thx"
    r")\b",
    re.I,
)

# Punctuation to remove (keep hyphens for compound words)
_PUNCT_TABLE = str.maketrans("", "", string.punctuation.replace("-", ""))


def normalize_text(text: str) -> str:
    """Lowercase, strip filler/punctuation, collapse whitespace."""
    result = text.lower().strip()
    result = result.translate(_PUNCT_TABLE)
    result = _FILLER_RE.sub(" ", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def tokenize(text: str) -> list[str]:
    return text.split()


# ── Fuzzy matching ────────────────────────────────────────────────


def fuzzy_match_token(token: str, target: str, threshold: float = 0.82) -> float:
    """Return similarity ratio if >= threshold, else 0.0.

    For short tokens (<=5 chars), a lower threshold is used automatically
    because single-char transpositions cause a bigger ratio drop.
    """
    if token == target:
        return 1.0
    effective = threshold
    if len(token) <= 5 or len(target) <= 5:
        effective = min(threshold, 0.72)
    ratio = SequenceMatcher(None, token, target).ratio()
    return ratio if ratio >= effective else 0.0


def find_best_match(
    tokens: list[str],
    candidates: set[str],
    threshold: float = 0.82,
) -> tuple[str, float]:
    """Return (best_matched_term, best_score) across all candidates."""
    best_term = ""
    best_score = 0.0
    text = " ".join(tokens)

    for candidate in candidates:
        parts = candidate.split()
        if len(parts) == 1:
            for token in tokens:
                if token == candidate:
                    return (candidate, 1.0)
                score = fuzzy_match_token(token, candidate, threshold)
                if score > best_score:
                    best_score = score
                    best_term = candidate
        else:
            # Multi-word candidate — substring or fuzzy window
            if candidate in text:
                return (candidate, 1.0)
            for i in range(len(tokens) - len(parts) + 1):
                window = " ".join(tokens[i : i + len(parts)])
                score = SequenceMatcher(None, window, candidate).ratio()
                if score >= threshold and score > best_score:
                    best_score = score
                    best_term = candidate

    return (best_term, best_score)


# ── Code-intent detection ─────────────────────────────────────────


def detect_code_intent(
    normalized: str,
    tokens: list[str],
    negative_terms: set[str],
) -> str:
    """Return the matched code-intent term, or '' if none detected.

    Uses exact matching for single-word terms (these are common English
    words unlikely to be misspelled, and fuzzy matching would cause false
    positives like 'remote' matching 'route').
    """
    # Multi-word phrases first (substring match on normalized text)
    for phrase in CODE_INTENT_PHRASES:
        if phrase in normalized:
            return phrase

    # Single-word negative terms — exact match only
    for term in negative_terms:
        if term in tokens:
            return term

    return ""


# ── Scoring ───────────────────────────────────────────────────────


def score_pattern(
    normalized: str,
    tokens: list[str],
    pattern: DirectActionPattern,
) -> ClassificationResult:
    """Score a prompt against one action pattern."""

    # 1. Code-implementation override
    negative = detect_code_intent(normalized, tokens, pattern.negative_code_terms)
    if negative:
        return ClassificationResult(
            action_name=pattern.action_name,
            task_class="code_implementation",
            confidence=0.0,
            negative_match=negative,
        )

    # 2. Verb match
    verb_term, verb_score = find_best_match(tokens, pattern.positive_verbs)

    # 3. Noun match
    noun_term, noun_score = find_best_match(tokens, pattern.positive_nouns)

    # 4. Context match (optional boost)
    ctx_term, ctx_score = find_best_match(tokens, pattern.context_terms)

    # 5. Confidence
    if not verb_term and not noun_term:
        return ClassificationResult(action_name="", task_class="", confidence=0.0)

    # Need at least one verb AND one noun for a real direct-action signal
    if not verb_term or not noun_term:
        base = max(verb_score, noun_score) * 0.45
        return ClassificationResult(
            action_name=pattern.action_name,
            task_class=pattern.task_class,
            confidence=base,
            matched_verb=verb_term,
            matched_noun=noun_term,
        )

    # Both verb and noun matched
    base = verb_score * 0.45 + noun_score * 0.45
    if ctx_term:
        base += ctx_score * 0.10

    return ClassificationResult(
        action_name=pattern.action_name,
        task_class=pattern.task_class,
        confidence=min(base, 1.0),
        matched_verb=verb_term,
        matched_noun=noun_term,
        matched_context=ctx_term,
    )


# ── Main classifier ──────────────────────────────────────────────


def classify_direct_action(
    prompt: str,
    patterns: list[DirectActionPattern] | None = None,
) -> ClassificationResult:
    """Classify a prompt as a direct platform action (or not).

    Returns the highest-confidence result.  If code-intent is detected
    for any pattern, returns immediately with confidence=0.0.
    """
    if patterns is None:
        patterns = DIRECT_ACTION_PATTERNS

    normalized = normalize_text(prompt)
    tokens = tokenize(normalized)

    if not tokens:
        return ClassificationResult(action_name="", task_class="", confidence=0.0)

    best: ClassificationResult | None = None

    for pattern in patterns:
        result = score_pattern(normalized, tokens, pattern)

        # Code intent → return immediately
        if result.is_code_intent:
            return result

        if best is None or result.confidence > best.confidence:
            best = result

    return best or ClassificationResult(action_name="", task_class="", confidence=0.0)


def should_execute_directly(result: ClassificationResult) -> bool:
    """True if confidence is high enough for direct execution."""
    if result.is_code_intent or not result.action_name:
        return False

    # Look up whether this action is low-risk
    threshold = DIRECT_THRESHOLD
    for p in DIRECT_ACTION_PATTERNS:
        if p.action_name == result.action_name and p.low_risk:
            threshold = LOW_RISK_DIRECT_THRESHOLD
            break

    return result.confidence >= threshold
