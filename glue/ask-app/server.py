#!/usr/bin/env python3
"""
"Ask the Running App" MCP Server — Query live app state via CDP.

Enables agents to query the running application directly:
  - What route am I on?
  - What component rendered this?
  - What network requests fired?
  - What console errors exist?
  - What localStorage keys changed?
  - What React props does this component have?

Uses Chrome DevTools Protocol to inspect the live browser session.

MCP Tools:
  ask_route           — What route/URL is currently showing?
  ask_component       — What React component rendered a selector?
  ask_network         — What network requests fired recently?
  ask_console         — Any console errors or warnings?
  ask_storage         — What's in localStorage/sessionStorage?
  ask_props           — What props does a component have?
  ask_state           — What's the React state of a component?
  ask_dom             — Get DOM info about a selector
  ask_performance     — Performance metrics (LCP, FID, CLS)
  ask_cookies         — What cookies are set?
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


def run_js_in_browser(script):
    """Execute JavaScript in Chrome via CDP and return result."""
    node_code = f"""
const http = require('http');

function fetch(url) {{
    return new Promise((resolve, reject) => {{
        http.get(url, (res) => {{
            let data = '';
            res.on('data', (chunk) => data += chunk);
            res.on('end', () => resolve(JSON.parse(data)));
        }}).on('error', reject);
    }});
}}

async function main() {{
    try {{
        const targets = await fetch('http://localhost:{CDP_PORT}/json');
        const page = targets.find(t => t.type === 'page');
        if (!page) {{ console.log(JSON.stringify({{error: 'no page target'}})); return; }}

        const WebSocket = require('ws');
        const ws = new WebSocket(page.webSocketDebuggerUrl);

        ws.on('open', () => {{
            ws.send(JSON.stringify({{
                id: 1,
                method: 'Runtime.evaluate',
                params: {{
                    expression: `{script.replace(chr(96), chr(92)+chr(96))}`,
                    returnByValue: true,
                    awaitPromise: true,
                }}
            }}));
        }});

        ws.on('message', (data) => {{
            const msg = JSON.parse(data);
            if (msg.id === 1) {{
                if (msg.result && msg.result.result) {{
                    console.log(JSON.stringify(msg.result.result.value || msg.result.result));
                }} else {{
                    console.log(JSON.stringify(msg));
                }}
                ws.close();
            }}
        }});

        setTimeout(() => {{ ws.close(); process.exit(1); }}, 10000);
    }} catch(e) {{
        console.log(JSON.stringify({{error: e.message}}));
    }}
}}
main();
"""
    try:
        result = subprocess.run(
            ["node", "-e", node_code],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": result.stdout.strip()}
        return {"error": result.stderr.strip() or "No output from browser"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout connecting to browser"}
    except FileNotFoundError:
        return {"error": "Node.js not available"}


def format_result(data):
    """Format result for MCP response."""
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2)


# --- Tool implementations ---

def tool_ask_route(args):
    result = run_js_in_browser("JSON.stringify({url: location.href, pathname: location.pathname, hash: location.hash, search: location.search, title: document.title})")
    return {"content": [{"type": "text", "text": f"Current route:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_component(args):
    selector = args.get("selector", "#root")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'Element not found: {selector}'}});
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
        if (!fiberKey) return JSON.stringify({{error: 'No React fiber found on element'}});
        const fiber = el[fiberKey];
        let current = fiber;
        const components = [];
        while (current && components.length < 5) {{
            if (current.type && typeof current.type === 'function') {{
                components.push({{
                    name: current.type.displayName || current.type.name || 'Anonymous',
                    props: Object.keys(current.memoizedProps || {{}})
                }});
            }}
            current = current.return;
        }}
        return JSON.stringify({{selector: '{selector}', components}});
    }})()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Components at `{selector}`:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_network(args):
    limit = args.get("limit", 20)
    script = f"""
    JSON.stringify(
        performance.getEntriesByType('resource').slice(-{limit}).map(e => ({{
            url: e.name.split('?')[0].split('/').slice(-2).join('/'),
            type: e.initiatorType,
            duration: Math.round(e.duration) + 'ms',
            size: e.transferSize ? Math.round(e.transferSize/1024) + 'KB' : '?',
            status: e.responseStatus || 0,
        }}))
    )
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Recent network requests:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_console(args):
    script = """
    (() => {
        if (!window.__console_capture) {
            window.__console_capture = [];
            const orig = {error: console.error, warn: console.warn};
            console.error = (...a) => { window.__console_capture.push({level:'error',msg:a.map(String).join(' '),time:Date.now()}); orig.error(...a); };
            console.warn = (...a) => { window.__console_capture.push({level:'warn',msg:a.map(String).join(' '),time:Date.now()}); orig.warn(...a); };
        }
        return JSON.stringify(window.__console_capture.slice(-20));
    })()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Console output:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_storage(args):
    storage_type = args.get("type", "both")
    script = f"""
    JSON.stringify({{
        {'localStorage: Object.fromEntries(Object.entries(localStorage).slice(0, 20)),' if storage_type in ('both', 'local') else ''}
        {'sessionStorage: Object.fromEntries(Object.entries(sessionStorage).slice(0, 20)),' if storage_type in ('both', 'session') else ''}
    }})
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Storage state:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_props(args):
    selector = args.get("selector", "#root > *")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'not found'}});
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
        if (!fiberKey) return JSON.stringify({{error: 'no fiber'}});
        let fiber = el[fiberKey];
        while (fiber && !(fiber.type && typeof fiber.type === 'function')) fiber = fiber.return;
        if (!fiber) return JSON.stringify({{error: 'no component fiber'}});
        const props = fiber.memoizedProps || {{}};
        const safe = {{}};
        for (const [k, v] of Object.entries(props)) {{
            if (typeof v === 'function') safe[k] = '[function]';
            else if (typeof v === 'object' && v !== null) safe[k] = JSON.stringify(v).substring(0, 100);
            else safe[k] = v;
        }}
        return JSON.stringify({{
            component: fiber.type.displayName || fiber.type.name || 'Anonymous',
            props: safe
        }});
    }})()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Props for `{selector}`:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_state(args):
    selector = args.get("selector", "#root > *")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'not found'}});
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
        if (!fiberKey) return JSON.stringify({{error: 'no fiber'}});
        let fiber = el[fiberKey];
        while (fiber && !(fiber.type && typeof fiber.type === 'function')) fiber = fiber.return;
        if (!fiber) return JSON.stringify({{error: 'no component'}});
        const state = fiber.memoizedState;
        const states = [];
        let hook = state;
        let i = 0;
        while (hook && i < 10) {{
            if (hook.memoizedState !== undefined && typeof hook.memoizedState !== 'function') {{
                states.push(hook.memoizedState);
            }}
            hook = hook.next;
            i++;
        }}
        return JSON.stringify({{
            component: fiber.type.displayName || fiber.type.name || 'Anonymous',
            hooks: states.slice(0, 5)
        }});
    }})()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"State for `{selector}`:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_dom(args):
    selector = args.get("selector", "body")
    script = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return JSON.stringify({{error: 'not found'}});
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return JSON.stringify({{
            tag: el.tagName.toLowerCase(),
            id: el.id,
            classes: [...el.classList],
            text: el.textContent?.substring(0, 200),
            children: el.children.length,
            visible: rect.width > 0 && rect.height > 0 && style.display !== 'none',
            rect: {{x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}},
            attributes: Object.fromEntries([...el.attributes].map(a => [a.name, a.value.substring(0, 50)])),
        }});
    }})()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"DOM info for `{selector}`:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_performance(args):
    script = """
    (() => {
        const nav = performance.getEntriesByType('navigation')[0] || {};
        const paint = performance.getEntriesByType('paint');
        const fcp = paint.find(e => e.name === 'first-contentful-paint');
        return JSON.stringify({
            domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime) + 'ms',
            load: Math.round(nav.loadEventEnd - nav.startTime) + 'ms',
            firstContentfulPaint: fcp ? Math.round(fcp.startTime) + 'ms' : 'N/A',
            domNodes: document.getElementsByTagName('*').length,
            jsHeapUsed: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1024 / 1024) + 'MB' : 'N/A',
            resourceCount: performance.getEntriesByType('resource').length,
        });
    })()
    """
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Performance:\n```json\n{format_result(result)}\n```"}]}


def tool_ask_cookies(args):
    script = """JSON.stringify(document.cookie.split(';').map(c => c.trim()).filter(Boolean).map(c => { const [k,...v] = c.split('='); return {name: k, value: v.join('=').substring(0, 50)}; }))"""
    result = run_js_in_browser(script)
    return {"content": [{"type": "text", "text": f"Cookies:\n```json\n{format_result(result)}\n```"}]}


# --- MCP Protocol ---

TOOLS = [
    {"name": "ask_route", "description": "What URL/route is currently showing in the browser?", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ask_component", "description": "What React component rendered a given element?", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector."}}, "required": ["selector"]}},
    {"name": "ask_network", "description": "What network requests fired recently?", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}},
    {"name": "ask_console", "description": "Any console errors or warnings? (installs capture hook on first call)", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ask_storage", "description": "What's in localStorage/sessionStorage?", "inputSchema": {"type": "object", "properties": {"type": {"type": "string", "enum": ["both", "local", "session"]}}}},
    {"name": "ask_props", "description": "What React props does the component at a selector have?", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "ask_state", "description": "What React hooks/state does a component have?", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "ask_dom", "description": "Get DOM info (tag, classes, rect, visibility, attributes) for a selector.", "inputSchema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "ask_performance", "description": "Get performance metrics (load time, FCP, heap, DOM nodes).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ask_cookies", "description": "What cookies are set on the current page?", "inputSchema": {"type": "object", "properties": {}}},
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
            "serverInfo": {"name": "ask-app-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "ask_route": tool_ask_route,
            "ask_component": tool_ask_component,
            "ask_network": tool_ask_network,
            "ask_console": tool_ask_console,
            "ask_storage": tool_ask_storage,
            "ask_props": tool_ask_props,
            "ask_state": tool_ask_state,
            "ask_dom": tool_ask_dom,
            "ask_performance": tool_ask_performance,
            "ask_cookies": tool_ask_cookies,
        }
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {name}"}}
        return {"jsonrpc": "2.0", "id": id, "result": handler(args)}
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
            sys.stderr.write(f"Ask App MCP error: {e}\n")


if __name__ == "__main__":
    main()
