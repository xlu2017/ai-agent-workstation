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

def write_session_context(session_id: str, event: dict):
    """Write event to session-specific context files."""
    session_dir = SESSIONS_DIR / session_id / "context"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Append to JSONL
    events_file = session_dir / "ui-events.jsonl"
    with open(events_file, "a") as f:
        f.write(json.dumps(event) + "\n")

    # Write human/agent-readable context
    md_file = session_dir / "latest-ui-context.md"
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
    event_dict = event.model_dump(by_alias=True)
    event_dict["timestamp"] = event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    event_dict["event_id"] = str(uuid.uuid4())

    log_event(event_dict)
    write_session_context(event.session_id, event_dict)

    return {"status": "ok", "event_id": event_dict["event_id"]}

@app.post("/inspect")
async def handle_inspect(event: UIEvent):
    event_dict = event.model_dump(by_alias=True)
    event_dict["type"] = "inspect"
    event_dict["timestamp"] = event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    event_dict["event_id"] = str(uuid.uuid4())

    log_event(event_dict)
    write_session_context(event.session_id, event_dict)

    return {"status": "ok", "event_id": event_dict["event_id"]}

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

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ui-bridge", "version": "0.2.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("UI_BRIDGE_PORT", "9876"))
    uvicorn.run(app, host="0.0.0.0", port=port)
