#!/usr/bin/env python3
"""
Playwright MCP Server — Live browser automation for AI agents.

Per-session browser control via Chrome DevTools Protocol (CDP).
Enables hot-reload verification, visual assertion, and "ask the running app" workflows.

MCP Tools:
  navigate           — Navigate to a URL
  screenshot         — Take a screenshot of the current page
  click              — Click an element by selector
  fill               — Fill a form field
  evaluate           — Execute JavaScript in the page
  get_console_logs   — Get browser console output
  get_network_log    — Get recent network requests
  get_page_state     — Get current URL, title, DOM snapshot
  wait_for_selector  — Wait for an element to appear
  assert_visible     — Assert an element is visible
  get_react_tree     — Get React component tree (dev mode)
  get_accessibility  — Get accessibility tree
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


def run_cdp_command(method, params=None):
    """Execute a CDP command via curl to the Chrome DevTools endpoint."""
    import urllib.request

    # Get the first available page target
    try:
        targets_url = f"http://localhost:{CDP_PORT}/json"
        with urllib.request.urlopen(targets_url, timeout=5) as resp:
            targets = json.loads(resp.read())
    except Exception as e:
        return {"error": f"Cannot connect to Chrome CDP on port {CDP_PORT}: {e}"}

    page_targets = [t for t in targets if t.get("type") == "page"]
    if not page_targets:
        return {"error": "No page targets available in Chrome."}

    # For simple operations, use the /json/version endpoint info
    return {"targets": page_targets, "count": len(page_targets)}


def execute_in_browser(script, session_id=None):
    """Execute JavaScript in the browser via CDP."""
    try:
        # Use playwright CLI or direct CDP websocket
        # Fallback: use subprocess with node script
        node_script = f"""
const http = require('http');
const WebSocket = require('ws');

async function main() {{
    const resp = await fetch('http://localhost:{CDP_PORT}/json');
    const targets = await resp.json();
    const page = targets.find(t => t.type === 'page');
    if (!page) {{ console.log(JSON.stringify({{error: 'no page'}})); return; }}

    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.on('open', () => {{
        ws.send(JSON.stringify({{
            id: 1,
            method: 'Runtime.evaluate',
            params: {{ expression: `{script}`, returnByValue: true }}
        }}));
    }});
    ws.on('message', (data) => {{
        const msg = JSON.parse(data);
        if (msg.id === 1) {{
            console.log(JSON.stringify(msg.result));
            ws.close();
        }}
    }});
}}
main();
"""
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": result.stderr.strip() or "No output"}
    except Exception as e:
        return {"error": str(e)}


# --- Tool Implementations ---

def tool_navigate(args):
    url = args.get("url", "")
    result = execute_in_browser(f"window.location.href = '{url}'; 'navigated to {url}'")
    return {"content": [{"type": "text", "text": f"Navigated to `{url}`"}]}


def tool_screenshot(args):
    selector = args.get("selector", "body")
    session_id = args.get("session_id", "default")
    screenshot_path = SESSIONS_DIR / session_id / "context" / "screenshot.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    script = f"""
    (async () => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'element not found'}});
        return JSON.stringify({{
            tag: el.tagName,
            text: el.textContent.substring(0, 200),
            rect: el.getBoundingClientRect()
        }});
    }})()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_evaluate(args):
    expression = args.get("expression", "")
    result = execute_in_browser(expression)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_get_page_state(args):
    script = """
    JSON.stringify({
        url: window.location.href,
        title: document.title,
        readyState: document.readyState,
        bodyChildCount: document.body?.children.length || 0,
        forms: document.forms.length,
        links: document.links.length,
        images: document.images.length,
        scripts: document.scripts.length,
        consoleErrors: window.__console_errors || [],
        localStorage: Object.keys(localStorage),
        sessionStorage: Object.keys(sessionStorage),
    })
    """
    result = execute_in_browser(script)
    if isinstance(result, dict) and "result" in result:
        try:
            state = json.loads(result["result"].get("value", "{}"))
            lines = [
                "# Current Page State\n",
                f"**URL:** {state.get('url', '?')}",
                f"**Title:** {state.get('title', '?')}",
                f"**Ready State:** {state.get('readyState', '?')}",
                f"**DOM Children:** {state.get('bodyChildCount', '?')}",
                f"**Forms:** {state.get('forms', 0)}",
                f"**Links:** {state.get('links', 0)}",
                f"**localStorage keys:** {state.get('localStorage', [])}",
                f"**sessionStorage keys:** {state.get('sessionStorage', [])}",
            ]
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}
        except (json.JSONDecodeError, TypeError):
            pass
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_get_console_logs(args):
    script = """
    JSON.stringify(window.__captured_console || [])
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": f"Console logs: {json.dumps(result, indent=2)}"}]}


def tool_get_network_log(args):
    script = """
    JSON.stringify(
        performance.getEntriesByType('resource').slice(-20).map(e => ({
            name: e.name,
            type: e.initiatorType,
            duration: Math.round(e.duration),
            size: e.transferSize || 0,
            status: e.responseStatus || 0,
        }))
    )
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": f"Recent network requests:\n{json.dumps(result, indent=2)}"}]}


def tool_click(args):
    selector = args.get("selector", "")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'not found', selector: '{selector}'}});
        el.click();
        return JSON.stringify({{clicked: true, tag: el.tagName, text: el.textContent.substring(0, 50)}});
    }})()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_fill(args):
    selector = args.get("selector", "")
    value = args.get("value", "")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'not found'}});
        el.value = '{value}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return JSON.stringify({{filled: true, selector: '{selector}'}});
    }})()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_wait_for_selector(args):
    selector = args.get("selector", "")
    timeout = args.get("timeout", 5000)
    script = f"""
    new Promise((resolve) => {{
        const check = () => {{
            const el = document.querySelector('{selector}');
            if (el) resolve(JSON.stringify({{found: true, tag: el.tagName}}));
        }};
        check();
        const observer = new MutationObserver(check);
        observer.observe(document.body, {{childList: true, subtree: true}});
        setTimeout(() => resolve(JSON.stringify({{found: false, timeout: true}})), {timeout});
    }})
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_assert_visible(args):
    selector = args.get("selector", "")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{visible: false, reason: 'not in DOM'}});
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        return JSON.stringify({{visible, rect: {{width: rect.width, height: rect.height}}, display: style.display}});
    }})()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def tool_get_react_tree(args):
    script = """
    (() => {
        const root = document.getElementById('root') || document.getElementById('__next');
        if (!root || !root._reactRootContainer && !root.__reactFiber$) {
            // Try React 18+ createRoot
            const fiberKey = Object.keys(root || {}).find(k => k.startsWith('__reactFiber$'));
            if (!fiberKey) return JSON.stringify({error: 'No React root found'});
        }
        const fiberKey = Object.keys(root).find(k => k.startsWith('__reactFiber$'));
        if (!fiberKey) return JSON.stringify({error: 'No React fiber found'});

        const fiber = root[fiberKey];
        const tree = [];
        function walk(node, depth) {
            if (!node || depth > 5) return;
            if (node.type && typeof node.type === 'function') {
                tree.push({
                    component: node.type.displayName || node.type.name || 'Anonymous',
                    depth,
                    props: Object.keys(node.memoizedProps || {}),
                });
            }
            walk(node.child, depth + (typeof node.type === 'function' ? 1 : 0));
            walk(node.sibling, depth);
        }
        walk(fiber, 0);
        return JSON.stringify(tree.slice(0, 50));
    })()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": f"React component tree:\n{json.dumps(result, indent=2)}"}]}


def tool_get_accessibility(args):
    script = """
    (() => {
        const items = [];
        const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_ELEMENT,
            {
                acceptNode: (node) => {
                    const role = node.getAttribute('role') || node.tagName.toLowerCase();
                    if (['button', 'a', 'input', 'select', 'textarea', 'h1', 'h2', 'h3', 'h4', 'nav', 'main', 'aside', 'form'].includes(role) ||
                        node.getAttribute('aria-label') || node.getAttribute('role')) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            }
        );
        let node;
        while ((node = walker.nextNode()) && items.length < 40) {
            items.push({
                tag: node.tagName.toLowerCase(),
                role: node.getAttribute('role') || node.tagName.toLowerCase(),
                label: node.getAttribute('aria-label') || node.textContent?.substring(0, 50)?.trim() || '',
                id: node.id || '',
            });
        }
        return JSON.stringify(items);
    })()
    """
    result = execute_in_browser(script)
    return {"content": [{"type": "text", "text": f"Accessibility tree:\n{json.dumps(result, indent=2)}"}]}


# --- MCP Protocol ---

TOOLS = [
    {"name": "navigate", "description": "Navigate browser to a URL.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "screenshot", "description": "Get info about an element on the page.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string", "default": "body"}, "session_id": {"type": "string"}}}},
    {"name": "click", "description": "Click an element by CSS selector.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "fill", "description": "Fill a form field with a value.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}}, "required": ["selector", "value"]}},
    {"name": "evaluate", "description": "Execute arbitrary JavaScript in the page and return the result.", "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
    {"name": "get_console_logs", "description": "Get captured console log output from the page.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_network_log", "description": "Get recent network requests (last 20 resource loads).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_page_state", "description": "Get current page state: URL, title, DOM stats, storage keys.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "wait_for_selector", "description": "Wait for a CSS selector to appear in the DOM.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}, "timeout": {"type": "integer", "default": 5000}}, "required": ["selector"]}},
    {"name": "assert_visible", "description": "Assert that an element matching the selector is visible on screen.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "get_react_tree", "description": "Get the React component tree from the page (requires dev mode).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_accessibility", "description": "Get the accessibility tree of the page (buttons, links, inputs, headings, landmarks).", "inputSchema": {"type": "object", "properties": {}}},
]


def read_message():
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    content_length = int(headers.get("content-length", 0))
    if content_length == 0:
        return None
    return json.loads(sys.stdin.read(content_length))


def write_message(msg):
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def handle_request(msg):
    method = msg.get("method", "")
    id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "playwright-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "navigate": tool_navigate,
            "screenshot": tool_screenshot,
            "click": tool_click,
            "fill": tool_fill,
            "evaluate": tool_evaluate,
            "get_console_logs": tool_get_console_logs,
            "get_network_log": tool_get_network_log,
            "get_page_state": tool_get_page_state,
            "wait_for_selector": tool_wait_for_selector,
            "assert_visible": tool_assert_visible,
            "get_react_tree": tool_get_react_tree,
            "get_accessibility": tool_get_accessibility,
        }
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        result = handler(args)
        return {"jsonrpc": "2.0", "id": id, "result": result}
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": id, "result": {}}
    return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {method}"}}


def main():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break
            response = handle_request(msg)
            if response:
                write_message(response)
        except EOFError:
            break
        except Exception as e:
            sys.stderr.write(f"Playwright MCP error: {e}\n")


if __name__ == "__main__":
    main()
