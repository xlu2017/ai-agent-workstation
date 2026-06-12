from __future__ import annotations

import json
import urllib.request
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


class BrowserCdpCollector:
    """Collect browser context without screenshots.

    Preferred production path: Playwright `page.context.new_cdp_session(page)` for
    CDP events and commands. This scaffold provides a dependency-free `/json/list`
    target poller so the control plane can start recording tab context before the
    full Playwright collector is enabled.
    """

    def __init__(self, debugging_url: str = "http://127.0.0.1:9222"):
        self.debugging_url = debugging_url.rstrip("/")

    def list_targets(self, timeout: float = 2.0) -> list[dict[str, Any]]:
        with urllib.request.urlopen(f"{self.debugging_url}/json/list", timeout=timeout) as response:
            data = json.loads(response.read().decode())
        if not isinstance(data, list):
            return []
        return [target for target in data if isinstance(target, dict)]

    def poll_tab_events(
        self,
        session_id: str,
        repo_id: str | None = None,
        worktree_id: str | None = None,
        branch: str | None = None,
    ) -> list[AmbientEvent]:
        events: list[AmbientEvent] = []
        for target in self.list_targets():
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
                        "target_id": target.get("id"),
                        "title": target.get("title"),
                        "url": target.get("url"),
                        "web_socket_debugger_url": target.get("webSocketDebuggerUrl"),
                    },
                )
            )
        return events


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
