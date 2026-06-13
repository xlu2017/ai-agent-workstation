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
                            events.extend(self._events_from_playwright_page(session_id, page, debugging_url, repo_id, worktree_id, branch))
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

    def _events_from_playwright_page(self, session_id: str, page, debugging_url: str, repo_id: str | None, worktree_id: str | None, branch: str | None) -> list[AmbientEvent]:
        page_state = self._collect_page_state(page)
        cdp_state = self._collect_cdp_state(page)
        try:
            title = page.title()
        except Exception:
            title = page_state.get("title")

        url = getattr(page, "url", None) or page_state.get("url")
        events = [
            AmbientEvent(
                event_type=AmbientEventType.BROWSER_TAB_OBSERVED.value,
                session_id=session_id,
                source=AmbientSource.BROWSER,
                repo_id=repo_id,
                worktree_id=worktree_id,
                branch=branch,
                confidence=0.92,
                payload={
                    "available": True,
                    "provider": "playwright_python",
                    "debugging_url": debugging_url,
                    "title": title,
                    "url": url,
                    "page_state": page_state,
                    "accessibility": cdp_state.get("accessibility"),
                    "dom_snapshot": cdp_state.get("dom_snapshot"),
                    "collector_notes": cdp_state.get("collector_notes", []),
                },
            )
        ]

        for request in page_state.get("networkRequests", [])[:50]:
            if not isinstance(request, dict):
                continue
            events.append(
                AmbientEvent(
                    event_type=AmbientEventType.BROWSER_NETWORK_REQUEST.value,
                    session_id=session_id,
                    source=AmbientSource.BROWSER,
                    repo_id=repo_id,
                    worktree_id=worktree_id,
                    branch=branch,
                    confidence=0.72,
                    payload={
                        "provider": "playwright_python.performance_entries",
                        "page_url": url,
                        "request": request,
                    },
                )
            )

        for item in page_state.get("consoleEvents", [])[:50]:
            if not isinstance(item, dict):
                continue
            events.append(
                AmbientEvent(
                    event_type=AmbientEventType.BROWSER_CONSOLE_LOG.value,
                    session_id=session_id,
                    source=AmbientSource.BROWSER,
                    repo_id=repo_id,
                    worktree_id=worktree_id,
                    branch=branch,
                    confidence=0.65,
                    payload={
                        "provider": "playwright_python.injected_console_ring",
                        "page_url": url,
                        "level": item.get("level"),
                        "message": item.get("message"),
                        "timestamp": item.get("timestamp"),
                    },
                )
            )
        return events

    def _event_from_playwright_page(self, session_id: str, page, debugging_url: str, repo_id: str | None, worktree_id: str | None, branch: str | None) -> AmbientEvent:
        """Backward-compatible wrapper for older tests/imports."""
        return self._events_from_playwright_page(session_id, page, debugging_url, repo_id, worktree_id, branch)[0]

    def _collect_page_state(self, page) -> dict[str, Any]:
        try:
            return page.evaluate(
                """
                () => {
                  if (!window.__JG_AMBIENT_CONSOLE_HOOK__) {
                    window.__JG_AMBIENT_CONSOLE_EVENTS__ = window.__JG_AMBIENT_CONSOLE_EVENTS__ || [];
                    const levels = ['log', 'info', 'warn', 'error'];
                    for (const level of levels) {
                      const original = console[level];
                      console[level] = function(...args) {
                        try {
                          window.__JG_AMBIENT_CONSOLE_EVENTS__.push({
                            level,
                            message: args.map((arg) => {
                              try { return typeof arg === 'string' ? arg : JSON.stringify(arg); }
                              catch (_) { return String(arg); }
                            }).join(' ').slice(0, 1000),
                            timestamp: new Date().toISOString(),
                          });
                          if (window.__JG_AMBIENT_CONSOLE_EVENTS__.length > 100) window.__JG_AMBIENT_CONSOLE_EVENTS__.shift();
                        } catch (_) {}
                        return original.apply(console, args);
                      };
                    }
                    window.__JG_AMBIENT_CONSOLE_HOOK__ = true;
                  }

                  const sourceHintFor = (node) => ({
                    componentName: node.getAttribute('data-component') || node.getAttribute('data-jg-component') || '',
                    sourceFile: node.getAttribute('data-source') || node.getAttribute('data-jg-source') || node.getAttribute('data-source-file') || '',
                    sourceLine: Number(node.getAttribute('data-source-line') || node.getAttribute('data-jg-line') || 0) || null,
                  });
                  const rectFor = (node) => {
                    const b = node.getBoundingClientRect();
                    return { x: b.left, y: b.top, width: b.width, height: b.height };
                  };
                  const active = document.activeElement;
                  const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map((node) => ({ text: node.textContent?.trim()?.slice(0, 120) || '', href: node.href }));
                  const interactive = Array.from(document.querySelectorAll('button,[role=button],input,textarea,select,a[href],[data-testid],[data-test]')).slice(0, 60).map((node) => ({
                    tagName: node.tagName.toLowerCase(),
                    text: node.textContent?.trim()?.slice(0, 160) || node.value || '',
                    role: node.getAttribute('role') || '',
                    ariaLabel: node.getAttribute('aria-label') || '',
                    id: node.id || '',
                    className: typeof node.className === 'string' ? node.className : '',
                    testId: node.getAttribute('data-testid') || node.getAttribute('data-test') || '',
                    name: node.getAttribute('name') || '',
                    href: node.href || '',
                    bounds: rectFor(node),
                    sourceHint: sourceHintFor(node),
                  }));
                  const networkRequests = performance.getEntriesByType('resource').slice(-50).map((entry) => ({
                    name: entry.name,
                    initiatorType: entry.initiatorType,
                    startTime: Math.round(entry.startTime),
                    duration: Math.round(entry.duration),
                    transferSize: entry.transferSize || 0,
                    encodedBodySize: entry.encodedBodySize || 0,
                  }));
                  return {
                    readyState: document.readyState,
                    activeElement: active ? { tag: active.tagName, id: active.id || '', text: active.textContent?.trim()?.slice(0, 120) || '', name: active.getAttribute('name') || '', bounds: rectFor(active) } : null,
                    bodyTextTail: document.body?.innerText?.slice(-2000) || '',
                    title: document.title,
                    url: location.href,
                    links,
                    interactive,
                    buttons: interactive.filter((node) => ['button', 'input'].includes(node.tagName) || node.role === 'button').slice(0, 30),
                    networkRequests,
                    consoleEvents: (window.__JG_AMBIENT_CONSOLE_EVENTS__ || []).slice(-50),
                  };
                }
                """
            )
        except Exception as exc:
            return {"page_state_error": str(exc)[:240]}

    def _collect_cdp_state(self, page) -> dict[str, Any]:
        state: dict[str, Any] = {"collector_notes": []}
        try:
            session = page.context.new_cdp_session(page)
        except Exception as exc:
            return {"collector_notes": [f"new_cdp_session failed: {str(exc)[:120]}"]}

        try:
            ax = session.send("Accessibility.getFullAXTree")
            nodes = ax.get("nodes", []) if isinstance(ax, dict) else []
            state["accessibility"] = {
                "node_count": len(nodes),
                "nodes": [self._compact_ax_node(node) for node in nodes[:80] if isinstance(node, dict)],
            }
        except Exception as exc:
            state["collector_notes"].append(f"Accessibility.getFullAXTree failed: {str(exc)[:120]}")

        try:
            dom = session.send("DOM.getDocument", {"depth": 2, "pierce": True})
            root = dom.get("root") if isinstance(dom, dict) else None
            state["dom_snapshot"] = self._compact_dom_node(root) if isinstance(root, dict) else None
        except Exception as exc:
            state["collector_notes"].append(f"DOM.getDocument failed: {str(exc)[:120]}")

        try:
            session.detach()
        except Exception:
            pass
        return state

    def _compact_ax_node(self, node: dict[str, Any]) -> dict[str, Any]:
        def value_of(key: str) -> Any:
            value = node.get(key)
            if isinstance(value, dict):
                return value.get("value")
            return value

        return {
            "role": value_of("role"),
            "name": value_of("name"),
            "value": value_of("value"),
            "ignored": node.get("ignored"),
        }

    def _compact_dom_node(self, node: dict[str, Any] | None, depth: int = 0) -> dict[str, Any] | None:
        if not node or depth > 2:
            return None
        attrs = node.get("attributes") or []
        attr_dict = {}
        if isinstance(attrs, list):
            for index in range(0, min(len(attrs), 20), 2):
                key = attrs[index]
                value = attrs[index + 1] if index + 1 < len(attrs) else ""
                if key in {"id", "class", "role", "aria-label", "data-testid", "data-test", "data-source", "data-component"}:
                    attr_dict[key] = value
        children = node.get("children") or []
        return {
            "nodeName": node.get("nodeName"),
            "nodeType": node.get("nodeType"),
            "attributes": attr_dict,
            "children": [self._compact_dom_node(child, depth + 1) for child in children[:20] if isinstance(child, dict)],
        }


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
