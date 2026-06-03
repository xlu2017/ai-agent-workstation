#!/usr/bin/env python3
"""
Knowledge/Memory System — Self-updating project memory with YAML triggers.

Stores durable lessons learned from agent sessions as YAML knowledge entries.
Activates relevant knowledge based on file paths, keywords, and packages.
Generates postmortems after failed agent runs.

Components:
  - Knowledge store (YAML files in /opt/workstation/knowledge/)
  - Activation engine (matches task context to relevant knowledge)
  - Postmortem generator (analyzes failed sessions, suggests new knowledge)
  - MCP server for agent access
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


# --- Knowledge Store ---

def load_all_knowledge():
    """Load all knowledge entries from YAML files."""
    entries = []
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
                if isinstance(data, list):
                    entries.extend(data)
                elif isinstance(data, dict):
                    entries.append(data)
        except (yaml.YAMLError, OSError):
            continue
    return entries


def save_knowledge_entry(entry, filename=None):
    """Save a knowledge entry to a YAML file."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        entry_id = entry.get("id", f"k-{int(time.time())}")
        filename = f"{entry_id}.yaml"
    filepath = KNOWLEDGE_DIR / filename
    with open(filepath, "w") as f:
        yaml.dump(entry, f, default_flow_style=False, sort_keys=False)
    return str(filepath)


def activate_knowledge(context):
    """Find knowledge entries relevant to the given context."""
    entries = load_all_knowledge()
    file_paths = context.get("file_paths", [])
    keywords = context.get("keywords", [])
    packages = context.get("packages", [])
    task_description = context.get("task", "").lower()

    results = []
    for entry in entries:
        score = 0

        # Match activation paths
        activation_paths = entry.get("activation_paths", [])
        for ap in activation_paths:
            pattern = ap.replace("*", ".*")
            for fp in file_paths:
                if re.search(pattern, fp):
                    score += 3

        # Match activation keywords
        activation_keywords = entry.get("activation_keywords", [])
        for ak in activation_keywords:
            ak_lower = ak.lower()
            if ak_lower in task_description:
                score += 2
            for kw in keywords:
                if ak_lower == kw.lower():
                    score += 2

        # Match activation packages
        activation_packages = entry.get("activation_packages", [])
        for ap in activation_packages:
            if ap in packages:
                score += 2

        if score > 0:
            results.append({
                "entry": entry,
                "score": score,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# --- Postmortem Generator ---

def generate_postmortem(session_id):
    """Generate a postmortem analysis for a failed session."""
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        return {"error": f"Session '{session_id}' not found."}

    # Collect session artifacts
    events_dir = session_dir / "events"
    context_dir = session_dir / "context"
    meta_file = session_dir / "session.json"

    postmortem = {
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {},
        "terminal_errors": [],
        "ui_events": [],
        "editor_events": [],
        "analysis": {},
        "suggested_knowledge": [],
    }

    # Load session meta
    if meta_file.exists():
        postmortem["meta"] = json.loads(meta_file.read_text())

    # Load terminal errors
    terminal_events = events_dir / "terminal-events.jsonl"
    if terminal_events.exists():
        for line in terminal_events.read_text().strip().split("\n"):
            if line.strip():
                try:
                    postmortem["terminal_errors"].append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Load UI events
    ui_events = events_dir / "ui-events.jsonl"
    if ui_events.exists():
        for line in ui_events.read_text().strip().split("\n"):
            if line.strip():
                try:
                    postmortem["ui_events"].append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Load editor events
    editor_events = events_dir / "editor-events.jsonl"
    if editor_events.exists():
        for line in editor_events.read_text().strip().split("\n"):
            if line.strip():
                try:
                    postmortem["editor_events"].append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Analyze patterns
    error_files = set()
    error_types = []
    for err_event in postmortem["terminal_errors"]:
        for error in err_event.get("errors", []):
            error_types.append(error.get("type", "unknown"))
            for f in error.get("files", []):
                error_files.add(f.get("file", ""))

    postmortem["analysis"] = {
        "total_errors": len(postmortem["terminal_errors"]),
        "error_types": list(set(error_types)),
        "files_with_errors": list(error_files),
        "ui_interactions": len(postmortem["ui_events"]),
        "editor_views": len(postmortem["editor_events"]),
    }

    # Suggest knowledge entries
    if error_files:
        postmortem["suggested_knowledge"].append({
            "id": f"k-{session_id}-errors",
            "description": f"Common errors in session {session_id}",
            "activation_paths": [f for f in error_files if f],
            "activation_keywords": error_types,
            "content": f"Session {session_id} encountered {len(postmortem['terminal_errors'])} errors in files: {', '.join(list(error_files)[:5])}",
            "confidence": "medium",
        })

    # Write postmortem
    postmortem_file = session_dir / "postmortem.json"
    with open(postmortem_file, "w") as f:
        json.dump(postmortem, f, indent=2)

    # Write markdown summary
    md_file = session_dir / "postmortem.md"
    md_content = generate_postmortem_md(postmortem)
    with open(md_file, "w") as f:
        f.write(md_content)

    return postmortem


def generate_postmortem_md(pm):
    """Generate markdown postmortem report."""
    lines = [
        f"# Postmortem: Session `{pm['session_id']}`",
        f"Generated: {pm['generated_at']}",
        "",
        "## Summary",
        f"- **Errors:** {pm['analysis'].get('total_errors', 0)}",
        f"- **Error types:** {', '.join(pm['analysis'].get('error_types', [])) or 'none'}",
        f"- **Files affected:** {', '.join(pm['analysis'].get('files_with_errors', [])[:5]) or 'none'}",
        f"- **UI interactions:** {pm['analysis'].get('ui_interactions', 0)}",
        f"- **Editor views:** {pm['analysis'].get('editor_views', 0)}",
        "",
    ]

    if pm["terminal_errors"]:
        lines.extend(["## Terminal Errors", ""])
        for i, err_event in enumerate(pm["terminal_errors"][:5], 1):
            cmd = err_event.get("command", "?")
            exit_code = err_event.get("exit_code", "?")
            lines.append(f"### Error {i}: `{cmd}` (exit {exit_code})")
            for error in err_event.get("errors", [])[:3]:
                lines.append(f"- {error.get('type', '?')}: `{error.get('message', '?')}`")
                for f in error.get("files", [])[:3]:
                    lines.append(f"  - `{f.get('file', '?')}:{f.get('line', '?')}`")
            lines.append("")

    if pm["suggested_knowledge"]:
        lines.extend(["## Suggested Knowledge Entries", ""])
        for entry in pm["suggested_knowledge"]:
            lines.append(f"```yaml")
            lines.append(yaml.dump(entry, default_flow_style=False).strip())
            lines.append("```")
            lines.append("")

    lines.extend([
        "## Recommendations",
        "",
        "- Review the files with errors and add defensive checks.",
        "- Approve suggested knowledge entries to prevent recurrence.",
        "- Consider adding test coverage for the affected paths.",
    ])

    return "\n".join(lines)


# --- MCP Tools ---

TOOLS = [
    {
        "name": "activate_knowledge",
        "description": "Find knowledge entries relevant to the current task context. Pass file paths, keywords, or a task description.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description."},
                "file_paths": {"type": "array", "items": {"type": "string"}, "description": "Files being worked on."},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "Relevant keywords."},
                "packages": {"type": "array", "items": {"type": "string"}, "description": "Package names in use."},
            },
        },
    },
    {
        "name": "add_knowledge",
        "description": "Add a new knowledge entry that will activate in future sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Unique ID for the entry."},
                "description": {"type": "string", "description": "What this knowledge is about."},
                "content": {"type": "string", "description": "The actual knowledge/guidance."},
                "activation_paths": {"type": "array", "items": {"type": "string"}, "description": "File path patterns that trigger this."},
                "activation_keywords": {"type": "array", "items": {"type": "string"}, "description": "Keywords that trigger this."},
                "activation_packages": {"type": "array", "items": {"type": "string"}, "description": "Package names that trigger this."},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["description", "content"],
        },
    },
    {
        "name": "list_knowledge",
        "description": "List all stored knowledge entries.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_postmortem",
        "description": "Generate a postmortem analysis for a session, identifying failures and suggesting knowledge improvements.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to analyze."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_postmortem",
        "description": "Get the postmortem report for a session (if generated).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID."},
            },
            "required": ["session_id"],
        },
    },
]


def handle_activate_knowledge(args):
    results = activate_knowledge(args)
    if not results:
        return {"content": [{"type": "text", "text": "No relevant knowledge found for this context."}]}
    lines = ["## Activated Knowledge\n"]
    for r in results[:10]:
        entry = r["entry"]
        lines.append(f"### {entry.get('description', '?')} (score: {r['score']})")
        lines.append(f"**ID:** {entry.get('id', '?')}")
        lines.append(f"**Confidence:** {entry.get('confidence', '?')}")
        lines.append(f"\n{entry.get('content', '')}\n")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_add_knowledge(args):
    entry = {
        "id": args.get("id", f"k-{int(time.time())}"),
        "description": args.get("description", ""),
        "content": args.get("content", ""),
        "activation_paths": args.get("activation_paths", []),
        "activation_keywords": args.get("activation_keywords", []),
        "activation_packages": args.get("activation_packages", []),
        "confidence": args.get("confidence", "medium"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    filepath = save_knowledge_entry(entry)
    return {"content": [{"type": "text", "text": f"Knowledge saved to `{filepath}`"}]}


def handle_list_knowledge(args):
    entries = load_all_knowledge()
    if not entries:
        return {"content": [{"type": "text", "text": "No knowledge entries stored."}]}
    lines = [f"## Knowledge Base ({len(entries)} entries)\n"]
    for e in entries:
        lines.append(f"- **{e.get('id', '?')}**: {e.get('description', '?')} [{e.get('confidence', '?')}]")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_generate_postmortem(args):
    session_id = args.get("session_id", "")
    pm = generate_postmortem(session_id)
    if "error" in pm:
        return {"content": [{"type": "text", "text": pm["error"]}]}
    md_file = SESSIONS_DIR / session_id / "postmortem.md"
    return {"content": [{"type": "text", "text": md_file.read_text()}]}


def handle_get_postmortem(args):
    session_id = args.get("session_id", "")
    md_file = SESSIONS_DIR / session_id / "postmortem.md"
    if md_file.exists():
        return {"content": [{"type": "text", "text": md_file.read_text()}]}
    return {"content": [{"type": "text", "text": f"No postmortem found for session '{session_id}'. Use generate_postmortem first."}]}


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
            "serverInfo": {"name": "knowledge-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "activate_knowledge": handle_activate_knowledge,
            "add_knowledge": handle_add_knowledge,
            "list_knowledge": handle_list_knowledge,
            "generate_postmortem": handle_generate_postmortem,
            "get_postmortem": handle_get_postmortem,
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
            sys.stderr.write(f"Knowledge MCP error: {e}\n")


if __name__ == "__main__":
    main()
