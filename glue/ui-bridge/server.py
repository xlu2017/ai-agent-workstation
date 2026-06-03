#!/usr/bin/env python3
"""
UI Bridge Service — Source-aware event router for agent sessions.

Receives UI selection/inspection events from the browser extension,
logs them as JSONL, and writes context files for agent consumption.

Endpoints:
  POST /selection       — Element selected in browser
  POST /inspect         — Element inspected via context menu
  GET  /events          — Stream recent events (optional ?session_id filter)
  GET  /sessions        — List known sessions
  POST /sessions/:id/context — Push context to a session manually

Runs on port 9876 (default, UI_BRIDGE_PORT env var).
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="UI Bridge Service", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
EVENTS_LOG = Path(os.environ.get("EVENTS_LOG", "/opt/workstation/glue/ui-bridge/events.jsonl"))


# --- Models ---

class ElementData(BaseModel):
    tag: str = ""
    id: str = ""
    class_name: str = Field("", alias="class")
    attributes: dict = {}
    text_content: str = ""
    xpath: str = ""

class SourceData(BaseModel):
    framework: str = ""
    component: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    confidence: str = "low"
    stack: list = []

class UIEvent(BaseModel):
    type: str  # "selection" | "inspect"
    session_id: str = "default"
    url: str = ""
    selected_text: str = ""
    element: ElementData = ElementData()
    source: SourceData = SourceData()
    timestamp: str = ""

class SessionInfo(BaseModel):
    id: str
    repo_path: str = ""
    worktree_path: str = ""
    branch: str = ""
    tmux_session: str = ""
    browser_profile: str = ""
    port_range: str = ""
    openhands_workspace: str = ""
    created_at: str = ""


# --- Helpers ---

def ensure_dirs():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)

def log_event(event: dict):
    ensure_dirs()
    with open(EVENTS_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")

def resolve_session_id(event_session_id: str, url: str) -> str:
    """Resolve the actual session from URL port, browser profile, or explicit ID."""
    # If explicit and not auto-generated, use it
    if event_session_id and not event_session_id.startswith("session-port-"):
        return event_session_id

    # Extract port from URL
    target_port = None
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            target_port = parsed.port
        except Exception:
            pass

    # Search sessions by port range
    if target_port:
        for session_dir in SESSIONS_DIR.iterdir():
            meta_file = session_dir / "session.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    port_range = meta.get("port_range", "")
                    if "-" in port_range:
                        start, end = port_range.split("-")
                        if int(start) <= target_port <= int(end):
                            return session_dir.name
                except (json.JSONDecodeError, OSError, ValueError):
                    continue

    # Fallback: use the most recently active session
    latest = None
    latest_time = 0
    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        meta_file = session_dir / "session.json"
        if meta_file.exists():
            mtime = meta_file.stat().st_mtime
            if mtime > latest_time:
                latest_time = mtime
                latest = session_dir.name

    if latest:
        return latest

    # Last resort: use the provided ID (creates session dir on write)
    return event_session_id or "default"


def write_session_context(session_id: str, event: dict):
    """Write event to session-specific context and events files."""
    base_dir = SESSIONS_DIR / session_id
    context_dir = base_dir / "context"
    events_dir = base_dir / "events"
    context_dir.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    # Append to JSONL in events/
    events_file = events_dir / "ui-events.jsonl"
    with open(events_file, "a") as f:
        f.write(json.dumps(event) + "\n")

    # Write human/agent-readable context in context/
    md_file = context_dir / "latest-ui-context.md"
    md_content = generate_context_md(event)
    with open(md_file, "w") as f:
        f.write(md_content)

def generate_context_md(event: dict) -> str:
    """Generate agent-readable markdown from a UI event."""
    lines = [
        "# Latest UI Context",
        "",
        f"**Event type:** {event.get('type', 'unknown')}",
        f"**Timestamp:** {event.get('timestamp', 'unknown')}",
        f"**URL:** {event.get('url', 'unknown')}",
        "",
    ]

    if event.get("selected_text"):
        lines.extend([
            "## Selected Text",
            "```",
            event["selected_text"],
            "```",
            "",
        ])

    element = event.get("element", {})
    if element.get("tag"):
        lines.extend([
            "## Element",
            f"- **Tag:** `<{element['tag']}>`",
            f"- **ID:** `{element.get('id', '')}`" if element.get("id") else "",
            f"- **Class:** `{element.get('class', '')}`" if element.get("class") else "",
            f"- **XPath:** `{element.get('xpath', '')}`" if element.get("xpath") else "",
            "",
        ])

    source = event.get("source", {})
    if source.get("file") or source.get("component"):
        confidence = source.get("confidence", "low")
        lines.extend([
            "## Source Resolution",
            f"- **Framework:** {source.get('framework', 'unknown')}",
            f"- **Component:** `{source.get('component', 'unknown')}`",
            f"- **File:** `{source.get('file', 'unknown')}`",
            f"- **Line:** {source.get('line', 'unknown')}",
            f"- **Column:** {source.get('column', 'unknown')}",
            f"- **Confidence:** {confidence}",
            "",
        ])

        stack = source.get("stack", [])
        if stack:
            lines.extend(["### Component Stack", ""])
            for frame in stack:
                lines.append(f"- `{frame.get('componentName', '?')}` at `{frame.get('filePath', '?')}:{frame.get('lineNumber', '?')}`")
            lines.append("")

    lines.extend([
        "## Suggested Agent Action",
        "",
    ])

    if source.get("file") and source.get("confidence") in ("medium", "high"):
        lines.append(f"Open `{source['file']}` at line {source.get('line', 1)} and inspect the `{source.get('component', '')}` component.")
    elif event.get("selected_text"):
        lines.append(f"Search the codebase for: `{event['selected_text'][:100]}`")
    else:
        lines.append(f"Inspect the `<{element.get('tag', 'unknown')}>` element on the current page.")

    lines.append("")
    return "\n".join(lines)

def get_sessions() -> list[dict]:
    """List all known sessions from JSON files."""
    ensure_dirs()
    sessions = []
    for f in SESSIONS_DIR.glob("*/session.json"):
        try:
            sessions.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


# --- Endpoints ---

@app.post("/selection")
async def handle_selection(event: UIEvent):
    resolved_session = resolve_session_id(event.session_id, event.url)
    event_dict = event.model_dump(by_alias=True)
    event_dict["session_id"] = resolved_session
    event_dict["timestamp"] = event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    event_dict["event_id"] = str(uuid.uuid4())

    log_event(event_dict)
    write_session_context(resolved_session, event_dict)

    return {"status": "ok", "event_id": event_dict["event_id"], "session_id": resolved_session}

@app.post("/inspect")
async def handle_inspect(event: UIEvent):
    resolved_session = resolve_session_id(event.session_id, event.url)
    event_dict = event.model_dump(by_alias=True)
    event_dict["type"] = "inspect"
    event_dict["session_id"] = resolved_session
    event_dict["timestamp"] = event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    event_dict["event_id"] = str(uuid.uuid4())

    log_event(event_dict)
    write_session_context(resolved_session, event_dict)

    return {"status": "ok", "event_id": event_dict["event_id"], "session_id": resolved_session}

@app.get("/events")
async def get_events(session_id: Optional[str] = Query(None), limit: int = Query(50)):
    """Return recent events, optionally filtered by session."""
    if not EVENTS_LOG.exists():
        return {"events": []}

    lines = EVENTS_LOG.read_text().strip().split("\n")
    events = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
            if session_id and ev.get("session_id") != session_id:
                continue
            events.append(ev)
            if len(events) >= limit:
                break
        except json.JSONDecodeError:
            continue

    return {"events": events}

@app.get("/sessions")
async def list_sessions():
    return {"sessions": get_sessions()}

@app.post("/sessions/{session_id}/context")
async def push_context(session_id: str, event: UIEvent):
    event_dict = event.model_dump(by_alias=True)
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    write_session_context(session_id, event_dict)
    return {"status": "ok", "session_id": session_id}

@app.post("/editor-context")
async def handle_editor_context(request: dict):
    """Receive editor focus/selection context from VS Code bridge extension."""
    session_id = resolve_session_id(request.get("session_id", ""), request.get("url", ""))
    request["session_id"] = session_id
    request["timestamp"] = request.get("timestamp") or datetime.now(timezone.utc).isoformat()

    # Write to session-specific files
    base_dir = SESSIONS_DIR / session_id
    context_dir = base_dir / "context"
    events_dir = base_dir / "events"
    context_dir.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    # Append to editor events JSONL
    jsonl_file = events_dir / "editor-events.jsonl"
    with open(jsonl_file, "a") as f:
        f.write(json.dumps(request) + "\n")

    # Write latest editor context markdown
    md_file = context_dir / "latest-editor-context.md"
    md_content = generate_editor_md(request)
    with open(md_file, "w") as f:
        f.write(md_content)

    return {"status": "ok", "session_id": session_id}


def generate_editor_md(event: dict) -> str:
    """Generate agent-readable markdown from an editor context event."""
    selection = event.get("selection", {})
    cursor = event.get("cursor", {})
    visible = event.get("visibleRange", {})
    diagnostics = event.get("diagnostics", [])

    lines = [
        "# Latest Editor Context",
        "",
        f"**File:** `{event.get('file', 'unknown')}`",
        f"**Language:** {event.get('language', 'unknown')}",
        f"**Branch:** {event.get('gitBranch', 'unknown')}",
        f"**Timestamp:** {event.get('timestamp', 'unknown')}",
        "",
        "## Cursor Position",
        f"Line {cursor.get('line', '?')}, Column {cursor.get('column', '?')}",
        f"**Symbol at cursor:** `{event.get('symbolAtCursor', '')}`",
        "",
    ]

    if selection.get("text"):
        lines.extend([
            "## Selected Text",
            f"Lines {selection.get('startLine', '?')}–{selection.get('endLine', '?')}:",
            "```",
            selection["text"][:2000],
            "```",
            "",
        ])

    if diagnostics:
        lines.extend(["## Diagnostics", ""])
        for diag in diagnostics[:10]:
            severity = diag.get("severity", "?")
            lines.append(f"- **{severity}** (line {diag.get('line', '?')}): {diag.get('message', '')}")
            if diag.get("source"):
                lines[-1] += f" [{diag['source']}]"
        lines.append("")

    lines.extend([
        "## Visible Range",
        f"Lines {visible.get('startLine', '?')}–{visible.get('endLine', '?')}",
        "",
        "## Suggested Agent Action",
        "",
    ])

    if selection.get("text"):
        lines.append(f"The user selected code in `{event.get('file', '?')}` (lines {selection.get('startLine', '?')}–{selection.get('endLine', '?')}). Focus on this selection.")
    elif diagnostics:
        diag = diagnostics[0]
        lines.append(f"There are diagnostics in `{event.get('file', '?')}`. Check line {diag.get('line', '?')}: {diag.get('message', '')}")
    else:
        lines.append(f"The user is viewing `{event.get('file', '?')}` at line {cursor.get('line', '?')}.")

    lines.append("")
    return "\n".join(lines)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ui-bridge", "version": "0.3.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("UI_BRIDGE_PORT", "9876"))
    uvicorn.run(app, host="0.0.0.0", port=port)
