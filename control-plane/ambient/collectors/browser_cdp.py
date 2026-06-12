from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource
from ambient.vendor_registry import ensure_vendor_python_path, provider_available


class BrowserCdpCollector:
    """Collect browser context without screenshots.

    The collector prefers vendored/installed Playwright when available so it can
    gather semantic page state from a CDP endpoint. It degrades to direct
    `/json/list` polling when Playwright is unavailable or a browser cannot be
    attached.
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
                    "provider": "direct_cdp",
                    "debugging_url": debugging_url,
                    "target_count": len(data),
                }
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                errors[debugging_url] = str(exc)[:240]
        return [], {"status": "unavailable", "provider": "direct_cdp", "debugging_urls": self.debugging_urls, "errors": errors}

    def poll_tab_events(
        self,
        session_id: str,
        repo_id: str | None = None,
        worktree_id: str | None = None,
        branch: str | None = None,
        timeout: float = 2.0,
    ) -> list[AmbientEvent]:
        playwright_events = self._poll_with_playwright(
            session_id,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=branch,
            timeout=timeout,
        )
        if playwright_events:
            return playwright_events

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
                        "provider": "direct_cdp",
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
                payload={"available": True, "provider": "direct_cdp", "health": health, "target_count": 0},
            )
        ]

    def _poll_with_playwright(
        self,
        session_id: str,
        *,
        repo_id: str | None,
        worktree_id: str | None,
        branch: str | None,
        timeout: float,
    ) -> list[AmbientEvent]:
        if not provider_available("playwright_python", "playwright"):
            return []
        ensure_vendor_python_path("playwright_python")
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception:
            return []

        errors: dict[str, str] = {}
        for debugging_url in self.debugging_urls:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(debugging_url, timeout=int(timeout * 1000))
                    events: list[AmbientEvent] = []
                    for context in browser.contexts:
                        for page in context.pages:
                            events.append(self._event_from_playwright_page(session_id, page, debugging_url, repo_id, worktree_id, branch))
                    browser.close()
                    if events:
                        return events
            except Exception as exc:  # PlaywrightError has broad subclasses across versions.
                errors[debugging_url] = str(exc)[:240]
                continue
        if errors:
            return [
                AmbientEvent(
                    event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
                    session_id=session_id,
                    source=AmbientSource.BROWSER,
                    repo_id=repo_id,
                    worktree_id=worktree_id,
                    branch=branch,
                    confidence=0.25,
                    payload={"available": False, "provider": "playwright_python", "errors": errors},
                )
            ]
        return []

    def _event_from_playwright_page(self, session_id: str, page, debugging_url: str, repo_id: str | None, worktree_id: str | None, branch: str | None) -> AmbientEvent:
        page_state: dict[str, Any] = {}
        try:
            page_state = page.evaluate(
                """
                () => {
                  const active = document.activeElement;
                  const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map((node) => ({ text: node.textContent?.trim()?.slice(0, 120) || '', href: node.href }));
                  const buttons = Array.from(document.querySelectorAll('button,[role=button],input[type=button],input[type=submit]')).slice(0, 30).map((node) => ({ text: node.textContent?.trim()?.slice(0, 120) || node.value || '', id: node.id || '', className: node.className || '', testId: node.getAttribute('data-testid') || '' }));
                  return {
                    readyState: document.readyState,
                    activeElement: active ? { tag: active.tagName, id: active.id || '', text: active.textContent?.trim()?.slice(0, 120) || '', name: active.getAttribute('name') || '' } : null,
                    bodyTextTail: document.body?.innerText?.slice(-2000) || '',
                    title: document.title,
                    url: location.href,
                    links,
                    buttons,
                  };
                }
                """
            )
        except Exception as exc:
            page_state = {"page_state_error": str(exc)[:240]}
        try:
            title = page.title()
        except Exception:
            title = page_state.get("title")
        return AmbientEvent(
            event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
            session_id=session_id,
            source=AmbientSource.BROWSER,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=branch,
            confidence=0.9,
            payload={
                "available": True,
                "provider": "playwright_python",
                "debugging_url": debugging_url,
                "title": title,
                "url": getattr(page, "url", None),
                "page_state": page_state,
            },
        )


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
