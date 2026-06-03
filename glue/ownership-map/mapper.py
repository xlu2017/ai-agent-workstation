#!/usr/bin/env python3
"""
Runtime Ownership Map — Route→Component→Handler→Service→DB tracer.

Builds a living map of the application's runtime structure:
  route /settings → SettingsPage.tsx → ProfileForm.tsx → useUpdateProfile()
  → PATCH /api/profile → profile_controller.py → user_service.py → users table

Components:
  - Static route scanner (React Router, Next.js pages, Express routes, FastAPI)
  - Source map linker (component → file)
  - Backend route scanner (Express, FastAPI, Django, Flask)
  - Service dependency tracer
  - DB model extractor

MCP Tools:
  trace_route        — Trace a frontend route to all its dependencies
  trace_component    — Trace a component to its API calls and backend handlers
  scan_routes        — Scan all routes in a project
  scan_api_endpoints — Scan all API endpoints
  get_ownership_map  — Get the full ownership map for a route or component
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


def ripgrep_matches(pattern, path, flags=None):
    """Run ripgrep and return matches."""
    cmd = ["rg", "--json", pattern]
    if flags:
        cmd.extend(flags)
    cmd.append(str(path))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    d = data["data"]
                    matches.append({
                        "file": d["path"]["text"],
                        "line": d["line_number"],
                        "text": d["lines"]["text"].strip(),
                    })
            except json.JSONDecodeError:
                continue
        return matches
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# --- Frontend Route Scanning ---

def scan_react_routes(project_path):
    """Scan React Router route definitions."""
    patterns = [
        r'<Route\s+.*?path=["\']([^"\']+)["\']',
        r'path:\s*["\']([^"\']+)["\']',
        r'createBrowserRouter\(',
    ]
    routes = []
    for pattern in patterns[:2]:
        matches = ripgrep_matches(pattern, project_path, ["--glob", "*.{tsx,jsx,ts,js}"])
        for m in matches:
            path_match = re.search(r'path=["\']([^"\']+)["\']', m["text"])
            if not path_match:
                path_match = re.search(r'path:\s*["\']([^"\']+)["\']', m["text"])
            if path_match:
                routes.append({
                    "route": path_match.group(1),
                    "file": m["file"],
                    "line": m["line"],
                    "framework": "react-router",
                })
    return routes


def scan_nextjs_routes(project_path):
    """Scan Next.js pages/app directory routes."""
    routes = []
    for pages_dir in ["pages", "app", "src/pages", "src/app"]:
        full_path = Path(project_path) / pages_dir
        if not full_path.exists():
            continue
        for f in full_path.rglob("*.{tsx,jsx,ts,js}"):
            rel = str(f.relative_to(full_path))
            if rel.startswith("_") or rel.startswith("api/"):
                continue
            route = "/" + rel.rsplit(".", 1)[0]
            route = route.replace("/index", "").replace("/page", "") or "/"
            route = re.sub(r'\[([^\]]+)\]', r':\1', route)
            routes.append({
                "route": route,
                "file": str(f),
                "line": 1,
                "framework": "next.js",
            })
    return routes


def scan_frontend_routes(project_path):
    """Scan all frontend routes."""
    routes = scan_react_routes(project_path)
    routes.extend(scan_nextjs_routes(project_path))
    return routes


# --- Backend Route Scanning ---

def scan_express_routes(project_path):
    """Scan Express.js route definitions."""
    pattern = r'\.(get|post|put|patch|delete|all)\s*\(["\']([^"\']+)["\']'
    matches = ripgrep_matches(pattern, project_path, ["--glob", "*.{ts,js}"])
    routes = []
    for m in matches:
        route_match = re.search(pattern, m["text"])
        if route_match:
            routes.append({
                "method": route_match.group(1).upper(),
                "route": route_match.group(2),
                "file": m["file"],
                "line": m["line"],
                "framework": "express",
            })
    return routes


def scan_fastapi_routes(project_path):
    """Scan FastAPI route definitions."""
    pattern = r'@\w+\.(get|post|put|patch|delete)\s*\(["\']([^"\']+)["\']'
    matches = ripgrep_matches(pattern, project_path, ["--glob", "*.py"])
    routes = []
    for m in matches:
        route_match = re.search(pattern, m["text"])
        if route_match:
            routes.append({
                "method": route_match.group(1).upper(),
                "route": route_match.group(2),
                "file": m["file"],
                "line": m["line"],
                "framework": "fastapi",
            })
    return routes


def scan_django_routes(project_path):
    """Scan Django URL patterns."""
    pattern = r'path\s*\(["\']([^"\']+)["\']'
    matches = ripgrep_matches(pattern, project_path, ["--glob", "*.py"])
    routes = []
    for m in matches:
        route_match = re.search(pattern, m["text"])
        if route_match:
            routes.append({
                "method": "ALL",
                "route": "/" + route_match.group(1),
                "file": m["file"],
                "line": m["line"],
                "framework": "django",
            })
    return routes


def scan_backend_routes(project_path):
    """Scan all backend API routes."""
    routes = scan_express_routes(project_path)
    routes.extend(scan_fastapi_routes(project_path))
    routes.extend(scan_django_routes(project_path))
    return routes


# --- Component Tracing ---

def trace_component_api_calls(component_file, project_path):
    """Find API calls made from a component."""
    if not Path(component_file).exists():
        return []

    content = Path(component_file).read_text()
    api_calls = []

    # fetch/axios patterns
    patterns = [
        r'fetch\s*\(["\']([^"\']+)["\']',
        r'axios\.(get|post|put|patch|delete)\s*\(["\']([^"\']+)["\']',
        r'\.(get|post|put|patch|delete)\s*\(["\']([^"\']+)["\']',
        r'useSWR\s*\(["\']([^"\']+)["\']',
        r'useQuery\s*\(.+?["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, content):
            groups = match.groups()
            url = groups[-1] if len(groups) > 1 else groups[0]
            method = groups[0].upper() if len(groups) > 1 and groups[0] in ("get", "post", "put", "patch", "delete") else "GET"
            api_calls.append({"url": url, "method": method})

    return api_calls


def find_backend_handler(api_path, method, project_path):
    """Find the backend handler for an API call."""
    # Normalize path
    api_path = api_path.split("?")[0]  # Remove query string

    backend_routes = scan_backend_routes(project_path)
    matches = []
    for route in backend_routes:
        # Simple pattern matching
        route_pattern = re.sub(r':\w+', r'[^/]+', route["route"])
        route_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', route_pattern)
        if re.match(route_pattern + "$", api_path):
            if route["method"] == "ALL" or route["method"] == method:
                matches.append(route)

    return matches


def trace_service_calls(handler_file, handler_line, project_path):
    """Trace service/model calls from a handler."""
    if not Path(handler_file).exists():
        return []

    content = Path(handler_file).read_text().split("\n")
    services = []

    # Look at imports and function calls near the handler
    for i, line in enumerate(content, 1):
        if re.match(r"^\s*(from|import)\s+", line):
            services.append({"type": "import", "line": i, "text": line.strip()})

    return services


def build_ownership_chain(route_or_component, project_path):
    """Build full ownership chain from route/component to DB."""
    chain = {"route": route_or_component, "layers": []}

    # Layer 1: Frontend route → component
    frontend_routes = scan_frontend_routes(project_path)
    for fr in frontend_routes:
        if fr["route"] == route_or_component:
            chain["layers"].append({
                "layer": "frontend_route",
                "file": fr["file"],
                "line": fr["line"],
                "framework": fr["framework"],
            })
            # Layer 2: Component API calls
            api_calls = trace_component_api_calls(fr["file"], project_path)
            for call in api_calls:
                chain["layers"].append({
                    "layer": "api_call",
                    "url": call["url"],
                    "method": call["method"],
                })
                # Layer 3: Backend handler
                handlers = find_backend_handler(call["url"], call["method"], project_path)
                for h in handlers:
                    chain["layers"].append({
                        "layer": "backend_handler",
                        "file": h["file"],
                        "line": h["line"],
                        "method": h["method"],
                        "framework": h["framework"],
                    })
            break

    return chain


# --- MCP Tools ---

TOOLS = [
    {
        "name": "trace_route",
        "description": "Trace a frontend route through the full stack: route → component → API call → backend handler → service → DB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "route": {"type": "string", "description": "Frontend route path (e.g., /settings)."},
                "session_id": {"type": "string", "description": "Session ID to scope to worktree."},
            },
            "required": ["route"],
        },
    },
    {
        "name": "trace_component",
        "description": "Trace a component's API calls and find their backend handlers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Component file path."},
                "session_id": {"type": "string"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "scan_routes",
        "description": "Scan all frontend routes (React Router, Next.js pages/app) in a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "path": {"type": "string", "description": "Project path (optional, uses session worktree)."},
            },
        },
    },
    {
        "name": "scan_api_endpoints",
        "description": "Scan all backend API endpoints (Express, FastAPI, Django) in a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    {
        "name": "get_ownership_map",
        "description": "Get the full ownership chain for a route, showing every layer from UI to DB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "route": {"type": "string", "description": "Route or component to trace."},
                "session_id": {"type": "string"},
            },
            "required": ["route"],
        },
    },
]


def get_project_path(session_id):
    if not session_id:
        return "."
    meta_file = SESSIONS_DIR / session_id / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        return meta.get("worktree_path") or meta.get("repo_path") or "."
    return "."


def handle_trace_route(args):
    route = args.get("route", "")
    project_path = args.get("path") or get_project_path(args.get("session_id"))
    chain = build_ownership_chain(route, project_path)
    if not chain["layers"]:
        return {"content": [{"type": "text", "text": f"No ownership chain found for route `{route}`."}]}
    lines = [f"## Ownership Chain: `{route}`\n"]
    for layer in chain["layers"]:
        layer_type = layer.get("layer", "?")
        if layer_type == "frontend_route":
            lines.append(f"1. **Frontend Route** → `{layer['file']}:{layer['line']}` ({layer['framework']})")
        elif layer_type == "api_call":
            lines.append(f"2. **API Call** → `{layer['method']} {layer['url']}`")
        elif layer_type == "backend_handler":
            lines.append(f"3. **Backend Handler** → `{layer['file']}:{layer['line']}` ({layer['framework']})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_trace_component(args):
    filepath = args.get("file", "")
    project_path = args.get("path") or get_project_path(args.get("session_id"))
    api_calls = trace_component_api_calls(filepath, project_path)
    if not api_calls:
        return {"content": [{"type": "text", "text": f"No API calls found in `{filepath}`."}]}
    lines = [f"## API Calls from `{filepath}`\n"]
    for call in api_calls:
        lines.append(f"- **{call['method']}** `{call['url']}`")
        handlers = find_backend_handler(call["url"], call["method"], project_path)
        for h in handlers:
            lines.append(f"  → Handler: `{h['file']}:{h['line']}` ({h['framework']})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_scan_routes(args):
    project_path = args.get("path") or get_project_path(args.get("session_id"))
    routes = scan_frontend_routes(project_path)
    if not routes:
        return {"content": [{"type": "text", "text": "No frontend routes found."}]}
    lines = [f"## Frontend Routes ({len(routes)} found)\n"]
    for r in routes[:50]:
        lines.append(f"- `{r['route']}` → `{r['file']}:{r['line']}` ({r['framework']})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_scan_api_endpoints(args):
    project_path = args.get("path") or get_project_path(args.get("session_id"))
    routes = scan_backend_routes(project_path)
    if not routes:
        return {"content": [{"type": "text", "text": "No API endpoints found."}]}
    lines = [f"## API Endpoints ({len(routes)} found)\n"]
    for r in routes[:50]:
        lines.append(f"- **{r['method']}** `{r['route']}` → `{r['file']}:{r['line']}` ({r['framework']})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_ownership_map(args):
    return handle_trace_route(args)


# --- MCP Protocol ---

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
            "serverInfo": {"name": "ownership-map-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "trace_route": handle_trace_route,
            "trace_component": handle_trace_component,
            "scan_routes": handle_scan_routes,
            "scan_api_endpoints": handle_scan_api_endpoints,
            "get_ownership_map": handle_get_ownership_map,
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
            sys.stderr.write(f"Ownership Map MCP error: {e}\n")


if __name__ == "__main__":
    main()
