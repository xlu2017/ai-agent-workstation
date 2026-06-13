from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambient.types import AmbientEvent

SOURCE_FILE_KEYS = ("sourceFile", "source_file", "source", "path")
TEXT_KEYS = ("text", "ariaLabel", "testId", "id", "componentName", "selector", "name")
SEARCH_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md"}
IGNORED_DIRS = {".git", "node_modules", ".venv", "dist", "build", "vendor", "coverage"}


@dataclass(frozen=True)
class SourceCandidate:
    path: str
    confidence: float
    reason: str
    event_id: str
    source: str = "ambient"
    line: int | None = None
    symbol: str | None = None
    selector: str | None = None
    text: str | None = None

    def model_dump(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 3),
            "reason": self.reason,
            "event_id": self.event_id,
            "source": self.source,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.symbol:
            data["symbol"] = self.symbol
        if self.selector:
            data["selector"] = self.selector
        if self.text:
            data["text"] = self.text[:240]
        return data


def build_source_candidates(
    events: list[AmbientEvent],
    *,
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    """Rank source-file candidates from ambient evidence.

    The resolver is intentionally deterministic. It converts explicit editor
    selections, browser source hints, selected DOM attributes, terminal-mentioned
    files, and optional worktree text matches into a compact list that can be
    placed in a context packet. It never authorizes file access or mutation.
    """

    candidates: list[SourceCandidate] = []
    worktree = _latest_worktree(events)

    for event in events:
        payload = event.payload or {}
        event_type = str(event.event_type)

        if event_type == "editor.selection_changed":
            path = _clean_path(payload.get("path"))
            if path:
                candidates.append(SourceCandidate(
                    path=path,
                    line=_int_or_none(payload.get("start_line")),
                    symbol=_str_or_none(payload.get("symbol")),
                    confidence=max(event.confidence, 0.95),
                    reason="active editor selection",
                    event_id=event.event_id,
                    source="editor",
                    text=_str_or_none(payload.get("selected_text")),
                ))

        if event_type == "browser.element_selected":
            candidates.extend(_browser_selection_candidates(event, worktree))

        if event_type == "browser.tab_observed":
            candidates.extend(_browser_page_state_candidates(event, worktree))

        if event_type == "terminal.command_completed":
            mentioned = payload.get("mentioned_files")
            if isinstance(mentioned, list):
                for path in mentioned:
                    clean = _clean_path(path)
                    if clean:
                        candidates.append(SourceCandidate(
                            path=clean,
                            confidence=min(0.85, max(0.55, event.confidence)),
                            reason="terminal output mentioned file",
                            event_id=event.event_id,
                            source="terminal",
                        ))

        if event_type.startswith("repo."):
            dirty_files = payload.get("dirty_files")
            if isinstance(dirty_files, list):
                for item in dirty_files:
                    if not isinstance(item, dict):
                        continue
                    clean = _clean_path(item.get("path"))
                    if clean:
                        candidates.append(SourceCandidate(
                            path=clean,
                            confidence=0.5,
                            reason="dirty file in current worktree",
                            event_id=event.event_id,
                            source="repo",
                        ))

    return [_dedupe_keyed(candidate).model_dump() for candidate in _rank_and_dedupe(candidates)[:max_candidates]]


def _browser_selection_candidates(event: AmbientEvent, worktree: Path | None) -> list[SourceCandidate]:
    payload = event.payload or {}
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        return []

    result: list[SourceCandidate] = []
    elements = selection.get("elements")
    if not isinstance(elements, list):
        return []

    for element in elements:
        if not isinstance(element, dict):
            continue
        normalized = _merge_source_hint(element)
        explicit = _explicit_source_candidate(normalized, event=event)
        if explicit:
            result.append(explicit)
            continue
        if worktree:
            result.extend(_worktree_text_candidates(event, normalized, worktree))
    return result


def _browser_page_state_candidates(event: AmbientEvent, worktree: Path | None) -> list[SourceCandidate]:
    payload = event.payload or {}
    page_state = payload.get("page_state")
    if not isinstance(page_state, dict):
        return []

    result: list[SourceCandidate] = []
    for element in _iter_page_state_elements(page_state):
        explicit = _explicit_source_candidate(
            element,
            event=event,
            reason="browser page-state source hint",
            source="browser_cdp",
        )
        if explicit:
            result.append(explicit)
            continue
        if worktree:
            result.extend(_worktree_text_candidates(event, element, worktree))
    return result


def _iter_page_state_elements(page_state: dict[str, Any]):
    seen: set[tuple[str, str, str, str]] = set()
    for key in ("interactive", "buttons"):
        values = page_state.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            element = _merge_source_hint(value)
            identity = (
                str(element.get("selector") or ""),
                str(element.get("testId") or ""),
                str(element.get("text") or ""),
                str(element.get("sourceFile") or ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            yield element


def _merge_source_hint(element: dict[str, Any]) -> dict[str, Any]:
    merged = dict(element)
    hint = merged.get("sourceHint") or merged.get("source_hint")
    if isinstance(hint, dict):
        for key in ("sourceFile", "source_file", "source", "path", "sourceLine", "line", "componentName", "sourceConfidence"):
            value = hint.get(key)
            if value not in (None, "") and not merged.get(key):
                merged[key] = value
    if not merged.get("selector") and merged.get("testId"):
        merged["selector"] = f"[data-testid={merged['testId']}]"
    return merged


def _explicit_source_candidate(
    element: dict[str, Any],
    *,
    event: AmbientEvent,
    reason: str = "browser selection source hint",
    source: str = "browser",
) -> SourceCandidate | None:
    for key in SOURCE_FILE_KEYS:
        clean = _clean_path(element.get(key))
        if clean:
            confidence = _float_or_default(element.get("sourceConfidence"), event.confidence)
            if key in {"sourceFile", "source_file", "source"}:
                confidence = max(confidence, 0.9)
            return SourceCandidate(
                path=clean,
                line=_int_or_none(element.get("sourceLine") or element.get("line")),
                symbol=_str_or_none(element.get("componentName")),
                selector=_str_or_none(element.get("selector")),
                text=_str_or_none(element.get("text")),
                confidence=confidence,
                reason=reason,
                event_id=event.event_id,
                source=source,
            )
    return None


def _worktree_text_candidates(event: AmbientEvent, element: dict[str, Any], worktree: Path) -> list[SourceCandidate]:
    terms = []
    for key in TEXT_KEYS:
        value = element.get(key)
        if isinstance(value, str) and len(value.strip()) >= 3:
            terms.append(value.strip())
    terms = _dedupe_terms(terms)
    if not terms:
        return []

    result: list[SourceCandidate] = []
    for path in _iter_searchable_files(worktree):
        rel = str(path.relative_to(worktree))
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        score = 0.0
        matched_term = ""
        for term in terms:
            if term and term in text:
                matched_term = term
                if term == element.get("componentName"):
                    score = max(score, 0.7)
                elif term == element.get("testId") or term == element.get("id"):
                    score = max(score, 0.65)
                elif term == element.get("selector"):
                    score = max(score, 0.55)
                else:
                    score = max(score, 0.45)
        if score > 0:
            result.append(SourceCandidate(
                path=rel,
                confidence=min(0.78, score),
                reason="browser selection text matched worktree file",
                event_id=event.event_id,
                source="worktree_search",
                symbol=_str_or_none(element.get("componentName")),
                selector=_str_or_none(element.get("selector")),
                text=matched_term,
            ))
    return result


def _iter_searchable_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SEARCH_SUFFIXES:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > 256_000:
                continue
        except OSError:
            continue
        yield path


def _latest_worktree(events: list[AmbientEvent]) -> Path | None:
    for event in reversed(events):
        if event.worktree_id:
            path = Path(event.worktree_id)
            if path.exists():
                return path
        payload = event.payload or {}
        for key in ("repo_root", "worktree", "worktree_path"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                path = Path(value)
                if path.exists():
                    return path
    return None


def _rank_and_dedupe(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    best: dict[tuple[str, int | None, str | None], SourceCandidate] = {}
    for candidate in candidates:
        normalized = _dedupe_keyed(candidate)
        key = (normalized.path, normalized.line, normalized.symbol)
        existing = best.get(key)
        if not existing or normalized.confidence > existing.confidence:
            best[key] = normalized
    return sorted(best.values(), key=lambda item: (-item.confidence, item.path, item.line or 0))


def _dedupe_keyed(candidate: SourceCandidate) -> SourceCandidate:
    return SourceCandidate(
        path=candidate.path.strip().lstrip("./"),
        confidence=candidate.confidence,
        reason=candidate.reason,
        event_id=candidate.event_id,
        source=candidate.source,
        line=candidate.line,
        symbol=candidate.symbol,
        selector=candidate.selector,
        text=candidate.text,
    )


def _dedupe_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    for term in terms:
        term = term.strip()
        if not term or term in result:
            continue
        if len(term) > 160:
            term = term[:160]
        result.append(term)
    return result[:8]


def _clean_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = value.strip()
    if not path or "\n" in path or len(path) > 240:
        return None
    if ":" in path:
        maybe_path, maybe_line = path.rsplit(":", 1)
        if maybe_line.isdigit():
            path = maybe_path
    if path.startswith("webpack://"):
        path = path.replace("webpack://", "", 1).lstrip("./")
    if path.startswith("file://"):
        path = path.replace("file://", "", 1)
    return path.lstrip("./")


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_or_default(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
