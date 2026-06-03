#!/usr/bin/env python3
"""
Session Black Box Recorder — Records everything that happens in a session.

Captures:
  - Commands executed and their output
  - File reads/writes
  - Git diffs and commits
  - Browser events
  - Editor focus changes
  - Terminal errors
  - Agent prompts/responses (via LiteLLM logs)

Provides replay and audit capabilities.

MCP Tools:
  start_recording    — Begin recording a session
  stop_recording     — Stop recording and finalize
  get_recording      — Get recording summary/timeline
  replay_session     — Replay key events from a session
  get_session_diff   — Get the final diff of a session
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


class SessionRecorder:
    def __init__(self, session_id):
        self.session_id = session_id
        self.session_dir = SESSIONS_DIR / session_id
        self.events_dir = self.session_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.recording_file = self.events_dir / "black-box.jsonl"
        self.meta_file = self.session_dir / "recording-meta.json"

    def record_event(self, event_type, data):
        """Record an event to the black box log."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        with open(self.recording_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def start(self):
        """Start a recording session."""
        meta = {
            "session_id": self.session_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "recording",
        }
        with open(self.meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        self.record_event("recording_started", {"session_id": self.session_id})
        return meta

    def stop(self):
        """Stop recording and generate summary."""
        meta = {}
        if self.meta_file.exists():
            meta = json.loads(self.meta_file.read_text())

        meta["stopped_at"] = datetime.now(timezone.utc).isoformat()
        meta["status"] = "completed"

        # Count events by type
        event_counts = {}
        total = 0
        if self.recording_file.exists():
            for line in self.recording_file.read_text().strip().split("\n"):
                if line.strip():
                    try:
                        ev = json.loads(line)
                        etype = ev.get("type", "unknown")
                        event_counts[etype] = event_counts.get(etype, 0) + 1
                        total += 1
                    except json.JSONDecodeError:
                        continue

        meta["event_counts"] = event_counts
        meta["total_events"] = total

        with open(self.meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        self.record_event("recording_stopped", meta)

        # Generate markdown summary
        self._generate_summary(meta)
        return meta

    def get_events(self, event_type=None, limit=50):
        """Get recorded events, optionally filtered by type."""
        events = []
        if not self.recording_file.exists():
            return events

        for line in self.recording_file.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
                if event_type is None or ev.get("type") == event_type:
                    events.append(ev)
            except json.JSONDecodeError:
                continue

        return events[-limit:]

    def get_git_diff(self, base="HEAD~5"):
        """Get the git diff for this session's worktree."""
        meta_file = self.session_dir / "session.json"
        if not meta_file.exists():
            return "No session metadata found."

        meta = json.loads(meta_file.read_text())
        repo_path = meta.get("worktree_path") or meta.get("repo_path")
        if not repo_path or not Path(repo_path).exists():
            return "No repo path found."

        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                capture_output=True, text=True, cwd=repo_path, timeout=10,
            )
            log = result.stdout.strip()

            result = subprocess.run(
                ["git", "diff", "--stat", base],
                capture_output=True, text=True, cwd=repo_path, timeout=10,
            )
            stat = result.stdout.strip()

            result = subprocess.run(
                ["git", "diff", base],
                capture_output=True, text=True, cwd=repo_path, timeout=10,
            )
            diff = result.stdout[:30000]

            return f"## Git Log\n```\n{log}\n```\n\n## Diff Stats\n```\n{stat}\n```\n\n## Full Diff\n```diff\n{diff}\n```"
        except Exception as e:
            return f"Error getting diff: {e}"

    def _generate_summary(self, meta):
        """Generate markdown summary of the recording."""
        events = self.get_events(limit=1000)

        lines = [
            f"# Session Recording: `{self.session_id}`",
            f"**Started:** {meta.get('started_at', '?')}",
            f"**Stopped:** {meta.get('stopped_at', '?')}",
            f"**Total events:** {meta.get('total_events', 0)}",
            "",
            "## Event Summary",
            "",
        ]

        for etype, count in sorted(meta.get("event_counts", {}).items()):
            lines.append(f"- {etype}: {count}")

        lines.extend(["", "## Timeline (last 20 events)", ""])

        for ev in events[-20:]:
            ts = ev.get("timestamp", "?")
            etype = ev.get("type", "?")
            data = ev.get("data", {})
            summary = ""
            if etype == "command":
                summary = f"`{data.get('cmd', '?')[:60]}` → exit {data.get('exit_code', '?')}"
            elif etype == "file_write":
                summary = f"wrote `{data.get('file', '?')}`"
            elif etype == "terminal_error":
                summary = f"error in `{data.get('command', '?')[:40]}`"
            elif etype == "ui_event":
                summary = f"{data.get('type', '?')} on `{data.get('url', '?')[:40]}`"
            elif etype == "editor_focus":
                summary = f"editing `{data.get('file', '?')}`"
            else:
                summary = json.dumps(data)[:60]
            lines.append(f"- `{ts[11:19]}` **{etype}**: {summary}")

        md_file = self.session_dir / "recording-summary.md"
        with open(md_file, "w") as f:
            f.write("\n".join(lines))


# --- MCP Tools ---

TOOLS = [
    {
        "name": "start_recording",
        "description": "Start recording events for a session (black box recorder).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to record."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "stop_recording",
        "description": "Stop recording and generate a summary for the session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "record_event",
        "description": "Record a single event to the session's black box.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "event_type": {"type": "string", "description": "Event type (command, file_write, error, etc)."},
                "data": {"type": "object", "description": "Event data."},
            },
            "required": ["session_id", "event_type", "data"],
        },
    },
    {
        "name": "get_recording",
        "description": "Get the recording summary and timeline for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "event_type": {"type": "string", "description": "Filter by event type (optional)."},
                "limit": {"type": "integer", "description": "Max events (default 50)."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_session_diff",
        "description": "Get the final git diff for a session (what changed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "base": {"type": "string", "description": "Base commit/ref to diff against (default: HEAD~5)."},
            },
            "required": ["session_id"],
        },
    },
]


def handle_start_recording(args):
    recorder = SessionRecorder(args["session_id"])
    meta = recorder.start()
    return {"content": [{"type": "text", "text": f"Recording started for session `{args['session_id']}`."}]}


def handle_stop_recording(args):
    recorder = SessionRecorder(args["session_id"])
    meta = recorder.stop()
    return {"content": [{"type": "text", "text": f"Recording stopped. {meta.get('total_events', 0)} events captured."}]}


def handle_record_event(args):
    recorder = SessionRecorder(args["session_id"])
    event = recorder.record_event(args["event_type"], args.get("data", {}))
    return {"content": [{"type": "text", "text": f"Event recorded: {args['event_type']}"}]}


def handle_get_recording(args):
    recorder = SessionRecorder(args["session_id"])
    summary_file = recorder.session_dir / "recording-summary.md"
    if summary_file.exists():
        return {"content": [{"type": "text", "text": summary_file.read_text()}]}
    events = recorder.get_events(
        event_type=args.get("event_type"),
        limit=args.get("limit", 50),
    )
    if not events:
        return {"content": [{"type": "text", "text": "No recording data found."}]}
    lines = [f"## Recording: {args['session_id']} ({len(events)} events)\n"]
    for ev in events[-20:]:
        lines.append(f"- `{ev.get('timestamp', '?')[11:19]}` **{ev.get('type', '?')}**")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_session_diff(args):
    recorder = SessionRecorder(args["session_id"])
    diff = recorder.get_git_diff(args.get("base", "HEAD~5"))
    return {"content": [{"type": "text", "text": diff}]}


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
            "serverInfo": {"name": "black-box-recorder-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "start_recording": handle_start_recording,
            "stop_recording": handle_stop_recording,
            "record_event": handle_record_event,
            "get_recording": handle_get_recording,
            "get_session_diff": handle_get_session_diff,
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
            sys.stderr.write(f"Recorder MCP error: {e}\n")


if __name__ == "__main__":
    main()
