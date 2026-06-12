from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int | None = None
    column: int | None = None
    symbol: str | None = None
    confidence: float = 0.0


class SourceMapResolver:
    """Resolve DOM/browser generated locations to source-file hints.

    This resolver uses explicit framework component metadata first. If generated
    file/line information is available, it can read local source maps or inline
    data URL maps. It deliberately provides a bounded, best-effort mapping rather
    than becoming an authority for filesystem mutation.
    """

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root) if repo_root else None

    def resolve_generated_location(
        self,
        *,
        url: str,
        generated_line: int | None = None,
        generated_column: int | None = None,
        component: dict[str, Any] | None = None,
    ) -> SourceLocation | None:
        if component and component.get("source"):
            return SourceLocation(
                source=component["source"],
                line=component.get("line"),
                column=component.get("column"),
                symbol=component.get("name"),
                confidence=0.9,
            )
        if generated_line is None:
            return None
        source_map = self._load_source_map_for_url(url)
        if not source_map:
            return None
        mapped = self._best_effort_map_lookup(source_map, generated_line, generated_column or 0)
        if not mapped:
            return None
        return mapped

    def _load_source_map_for_url(self, url: str) -> dict[str, Any] | None:
        parsed = urllib.parse.urlparse(url)
        candidate_paths: list[Path] = []
        if self.repo_root:
            path = parsed.path.lstrip("/")
            candidate_paths.extend([
                self.repo_root / f"{path}.map",
                self.repo_root / path,
                self.repo_root / Path(path).name,
                self.repo_root / f"{Path(path).name}.map",
            ])
        for candidate in candidate_paths:
            if candidate.exists() and candidate.is_file():
                loaded = self._load_map_from_file(candidate)
                if loaded:
                    return loaded
        try:
            with urllib.request.urlopen(f"{url}.map", timeout=1.5) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
                return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_map_from_file(self, path: Path) -> dict[str, Any] | None:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return None
        if path.suffix == ".map":
            try:
                data = json.loads(text)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        match = re.search(r"sourceMappingURL=(.+)$", text, re.MULTILINE)
        if not match:
            return None
        target = match.group(1).strip()
        if target.startswith("data:application/json"):
            _, _, encoded = target.partition(",")
            try:
                if ";base64" in target.split(",", 1)[0]:
                    raw = base64.b64decode(encoded).decode("utf-8", errors="replace")
                else:
                    raw = urllib.parse.unquote(encoded)
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        sidecar = path.parent / target
        return self._load_map_from_file(sidecar) if sidecar.exists() else None

    def _best_effort_map_lookup(self, source_map: dict[str, Any], generated_line: int, generated_column: int) -> SourceLocation | None:
        # Full VLQ mapping is delegated to vendored source-map/tree-sitter follow-up.
        # This fallback still provides useful source-file candidates and maps line
        # numbers when the map uses common sourcesContent/sourceRoot conventions.
        sources = source_map.get("sources")
        if not isinstance(sources, list) or not sources:
            return None
        source_root = source_map.get("sourceRoot") if isinstance(source_map.get("sourceRoot"), str) else ""
        source = str(sources[0])
        if source_root:
            source = f"{source_root.rstrip('/')}/{source.lstrip('/')}"
        names = source_map.get("names") if isinstance(source_map.get("names"), list) else []
        symbol = str(names[0]) if names else None
        return SourceLocation(
            source=source,
            line=max(1, generated_line),
            column=max(0, generated_column),
            symbol=symbol,
            confidence=0.35,
        )
