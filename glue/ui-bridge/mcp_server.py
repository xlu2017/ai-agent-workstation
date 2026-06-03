#!/usr/bin/env python3
"""
MCP Server for UI Bridge — Ambient Context for AI Agents.

Exposes tools that let an agent read the current UI focus context
without requiring any manual copy/paste from the user.

Tools:
  get_current_ui_focus       — Returns the latest UI element the user interacted with
  get_recent_ui_events       — Returns recent UI events (selection, inspect) for a session
  resolve_ui_focus_to_source — Resolves current focus to source file/component/line

This runs as a stdio-based MCP server (JSON-RPC over stdin/stdout).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


# --- MCP Protocol Implementation (stdio JSON-RPC) ---

def read_message():
    """Read a JSON-RPC message from stdin (Content-Length header protocol)."""
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

    body = sys.stdin.read(content_length)
    return json.loads(body)


def write_message(msg):
    """Write a JSON-RPC message to stdout."""
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def make_response(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# --- Session Resolution ---

def find_active_session(session_id=None, port=None, url=None):
    """Find the active session by ID, port, or URL."""
    if session_id:
        session_dir = SESSIONS_DIR / session_id
        if (session_dir / "session.json").exists():
            return session_id, json.loads((session_dir / "session.json").read_text())

    # Search by port
    if port or url:
        target_port = port
        if not target_port and url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                target_port = parsed.port
            except Exception:
                pass

        if target_port:
            for session_dir in SESSIONS_DIR.iterdir():
                meta_file = session_dir / "session.json"
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text())
                    port_range = meta.get("port_range", "")
                    if "-" in port_range:
                        start, end = port_range.split("-")
                        if int(start) <= int(target_port) <= int(end):
                            return session_dir.name, meta

    # Return the most recently modified session
    latest = None
    latest_time = 0
    for session_dir in SESSIONS_DIR.iterdir():
        context_file = session_dir / "context" / "latest-ui-context.md"
        events_file = session_dir / "events" / "ui-events.jsonl"
        for f in [context_file, events_file]:
            if f.exists() and f.stat().st_mtime > latest_time:
                latest_time = f.stat().st_mtime
                latest = session_dir.name

    if latest:
        meta_file = SESSIONS_DIR / latest / "session.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        return latest, meta

    return None, None


def get_latest_context(session_id):
    """Read the latest UI context markdown for a session."""
    # Check both new (events/) and old (context/) paths
    for subdir in ["context", "events"]:
        md_file = SESSIONS_DIR / session_id / subdir / "latest-ui-context.md"
        if md_file.exists():
            return md_file.read_text()
    return None


def get_events(session_id, limit=10):
    """Read recent UI events for a session."""
    events = []
    for subdir in ["events", "context"]:
        jsonl_file = SESSIONS_DIR / session_id / subdir / "ui-events.jsonl"
        if jsonl_file.exists():
            lines = jsonl_file.read_text().strip().split("\n")
            for line in reversed(lines):
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if len(events) >= limit:
                        break
            break
    return events


def get_latest_event(session_id):
    """Get the single most recent event."""
    events = get_events(session_id, limit=1)
    return events[0] if events else None


# --- Tool Implementations ---

def tool_get_current_ui_focus(arguments):
    """Returns the latest UI element the user interacted with."""
    session_id = arguments.get("session_id")
    url = arguments.get("url")
    port = arguments.get("port")

    sid, meta = find_active_session(session_id, port, url)
    if not sid:
        return {"content": [{"type": "text", "text": "No active session found. The user hasn't interacted with any UI element yet."}]}

    context_md = get_latest_context(sid)
    if not context_md:
        return {"content": [{"type": "text", "text": f"Session '{sid}' exists but no UI interactions recorded yet."}]}

    return {"content": [{"type": "text", "text": context_md}]}


def tool_get_recent_ui_events(arguments):
    """Returns recent UI events for the active session."""
    session_id = arguments.get("session_id")
    limit = arguments.get("limit", 10)
    url = arguments.get("url")

    sid, meta = find_active_session(session_id, url=url)
    if not sid:
        return {"content": [{"type": "text", "text": "No active session found."}]}

    events = get_events(sid, limit=limit)
    if not events:
        return {"content": [{"type": "text", "text": f"No UI events recorded for session '{sid}'."}]}

    # Format as readable summary
    lines = [f"## Recent UI Events (session: {sid})", ""]
    for i, ev in enumerate(events, 1):
        source = ev.get("source", {})
        element = ev.get("element", {})
        lines.append(f"### Event {i}: {ev.get('type', '?')}")
        lines.append(f"- **URL:** {ev.get('url', '?')}")
        lines.append(f"- **Time:** {ev.get('timestamp', '?')}")
        if ev.get("selected_text"):
            lines.append(f"- **Selected text:** \"{ev['selected_text'][:100]}\"")
        if element.get("tag"):
            lines.append(f"- **Element:** `<{element['tag']}>` id=`{element.get('id', '')}` class=`{element.get('class', '')}`")
        if source.get("component"):
            lines.append(f"- **Component:** `{source['component']}`")
        if source.get("file"):
            lines.append(f"- **File:** `{source['file']}:{source.get('line', '?')}`")
            lines.append(f"- **Confidence:** {source.get('confidence', 'low')}")
        lines.append("")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def tool_resolve_ui_focus_to_source(arguments):
    """Resolves current UI focus to source file/component/line."""
    session_id = arguments.get("session_id")
    url = arguments.get("url")

    sid, meta = find_active_session(session_id, url=url)
    if not sid:
        return {"content": [{"type": "text", "text": "No active session found."}]}

    event = get_latest_event(sid)
    if not event:
        return {"content": [{"type": "text", "text": "No UI events recorded."}]}

    source = event.get("source", {})
    element = event.get("element", {})

    result = {
        "session_id": sid,
        "url": event.get("url", ""),
        "event_type": event.get("type", ""),
        "timestamp": event.get("timestamp", ""),
        "element": {
            "tag": element.get("tag", ""),
            "id": element.get("id", ""),
            "class": element.get("class", ""),
            "text": event.get("selected_text", "") or element.get("text_content", ""),
        },
        "source": {
            "framework": source.get("framework", "unknown"),
            "component": source.get("component"),
            "file": source.get("file"),
            "line": source.get("line"),
            "column": source.get("column"),
            "confidence": source.get("confidence", "low"),
        },
        "worktree": meta.get("worktree_path", ""),
        "repo": meta.get("repo_path", ""),
    }

    # Build agent-friendly summary
    if source.get("file") and source.get("confidence") in ("medium", "high"):
        summary = f"The user is looking at `{source.get('component', element.get('tag', '?'))}` in `{source['file']}` (line {source.get('line', '?')}). "
        if event.get("selected_text"):
            summary += f"They selected: \"{event['selected_text'][:100]}\". "
        summary += "You can open this file and inspect the component."
    elif event.get("selected_text"):
        summary += f"The user selected text: \"{event['selected_text'][:100]}\" on `{event.get('url', '?')}`. Search the codebase for this text or the containing component."
    else:
        summary = f"The user interacted with a `<{element.get('tag', '?')}>` element on `{event.get('url', '?')}`. Source resolution confidence is {source.get('confidence', 'low')}."

    result["summary"] = summary
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# --- MCP Server Main Loop ---

TOOLS = [
    {
        "name": "get_current_ui_focus",
        "description": "Returns the latest UI element the user interacted with in the browser. Use this when the user says 'fix this', 'look at this', or refers to something they're seeing in the UI. Returns a markdown document with element metadata, source file/component if resolved, and suggested action.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Optional session ID. If omitted, uses the most recently active session."},
                "url": {"type": "string", "description": "Optional URL to match against active sessions."},
                "port": {"type": "integer", "description": "Optional dev server port to identify the session."},
            },
        },
    },
    {
        "name": "get_recent_ui_events",
        "description": "Returns a list of recent UI interaction events (selections, inspections) for the active session. Useful for understanding what the user has been looking at over time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Optional session ID."},
                "limit": {"type": "integer", "description": "Max events to return (default 10)."},
                "url": {"type": "string", "description": "Optional URL filter."},
            },
        },
    },
    {
        "name": "resolve_ui_focus_to_source",
        "description": "Resolves the current UI focus to a specific source file, component name, and line number. Returns structured data including the repo path, worktree, framework, and confidence level. Use this when you need precise source location to make code changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Optional session ID."},
                "url": {"type": "string", "description": "Optional URL to identify session."},
            },
        },
    },
]


def handle_request(msg):
    method = msg.get("method", "")
    id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return make_response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ui-bridge-mcp", "version": "0.2.0"},
        })

    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "tools/list":
        return make_response(id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "get_current_ui_focus":
            result = tool_get_current_ui_focus(arguments)
        elif tool_name == "get_recent_ui_events":
            result = tool_get_recent_ui_events(arguments)
        elif tool_name == "resolve_ui_focus_to_source":
            result = tool_resolve_ui_focus_to_source(arguments)
        else:
            return make_error(id, -32601, f"Unknown tool: {tool_name}")

        return make_response(id, result)

    elif method == "ping":
        return make_response(id, {})

    else:
        return make_error(id, -32601, f"Method not found: {method}")


def main():
    """Run MCP server over stdio."""
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
            sys.stderr.write(f"MCP server error: {e}\n")
            continue


if __name__ == "__main__":
    main()
