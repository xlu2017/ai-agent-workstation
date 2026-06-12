from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


class BrowserCdpCollector:
    """Collect browser context without screenshots.

    The collector accepts one or more Chrome DevTools endpoints and degrades
    cleanly when the browser is unavailable, restarted, or moved to another port.
    """

    def __init__(self, debugging_urls: str | list[str] | None = None):
        if debugging_urls is None:
            debugging_urls = ["http://127.0.0.1:9222"]
        if isinstance(debugging_urls, str):
            debugging_urls = [debugging_urls]
        self.debugging_urls = [url.rstrip("/") for url in debugging_urls if url]

    def list_targets(self, timeout: float = 2.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        errors: dict[str, str] = {}
        for debugging_url in self.debugging_urls:
            try:
                with urllib.request.urlopen(f"{debugging_url}/json/list", timeout=timeout) as response:
                    data = json.loads(response.read().decode())
                if not isinstance(data, list):
                    errors[debugging_url] = "CDP /json/list did not return a list"
                    continue
                return [target for target in data if isinstance(target, dict)], {
                    "status": "available",
                    "debugging_url": debugging_url,
                    "target_count": len(data),
                }
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                errors[debugging_url] = str(exc)[:240]
        return [], {"status": "unavailable", "debugging_urls": self.debugging_urls, "errors": errors}

    def poll_tab_events(
        self,
        session_id: str,
        repo_id: str | None = None,
        worktree_id: str | None = None,
        branch: str | None = None,
        timeout: float = 2.0,
    ) -> list[AmbientEvent]:
        events: list[AmbientEvent] = []
        targets, health = self.list_targets(timeout=timeout)
        if health.get("status") != "available":
            return [
                AmbientEvent(
                    event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
                    session_id=session_id,
                    source=AmbientSource.BROWSER,
                    repo_id=repo_id,
                    worktree_id=worktree_id,
                    branch=branch,
                    confidence=0.15,
                    payload={"available": False, "health": health},
                )
            ]

        for target in targets:
            if target.get("type") != "page":
                continue
            events.append(
                AmbientEvent(
                    event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
                    session_id=session_id,
                    source=AmbientSource.BROWSER,
                    repo_id=repo_id,
                    worktree_id=worktree_id,
                    branch=branch,
                    confidence=0.8,
                    payload={
                        "available": True,
                        "debugging_url": health.get("debugging_url"),
                        "target_id": target.get("id"),
                        "title": target.get("title"),
                        "url": target.get("url"),
                        "web_socket_debugger_url": target.get("webSocketDebuggerUrl"),
                    },
                )
            )
        return events or [
            AmbientEvent(
                event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
                session_id=session_id,
                source=AmbientSource.BROWSER,
                repo_id=repo_id,
                worktree_id=worktree_id,
                branch=branch,
                confidence=0.35,
                payload={"available": True, "health": health, "target_count": 0},
            )
        ]


def build_element_selected_event(
    session_id: str,
    *,
    url: str,
    selector: str,
    text: str | None = None,
    component: dict[str, Any] | None = None,
    dom_path: str | None = None,
    confidence: float = 0.9,
    repo_id: str | None = None,
    worktree_id: str | None = None,
    branch: str | None = None,
) -> AmbientEvent:
    """Build a browser element focus event from CDP/extension/frontend-SDK data."""

    return AmbientEvent(
        event_type=AmbientEventType.BROWSER_ELEMENT_SELECTED.value,
        session_id=session_id,
        source=AmbientSource.BROWSER,
        repo_id=repo_id,
        worktree_id=worktree_id,
        branch=branch,
        confidence=confidence,
        payload={
            "url": url,
            "selector": selector,
            "text": text,
            "component": component or {},
            "dom_path": dom_path,
        },
    )
