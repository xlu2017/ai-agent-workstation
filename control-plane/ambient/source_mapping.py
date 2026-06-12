from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int | None = None
    column: int | None = None
    symbol: str | None = None
    confidence: float = 0.0


class SourceMapResolver:
    """Interface for DOM/browser location to source-file resolution.

    Preferred implementation path:
    - use browser/CDP stack-frame locations when available;
    - resolve generated locations through existing source maps;
    - consult the ui-bridge service for repo-local file lookup;
    - enrich with framework SDK component metadata.

    This scaffold intentionally defines the contract without embedding a JS
    source-map runtime in the Python control plane.
    """

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
        return None
