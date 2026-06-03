#!/usr/bin/env python3
"""
Rewindable Development Timeline — Git-level checkpoints per session.

Before risky edits, the system snapshots the session. Allows rewinding
to any checkpoint without losing the full history.

Uses git commits + tags as the checkpoint mechanism (no nested VMs needed).

MCP Tools:
  create_checkpoint  — Snapshot current state before risky operation
  list_checkpoints   — List all checkpoints for a session
  rewind_to          — Rewind session to a specific checkpoint
  compare_checkpoints — Show diff between two checkpoints
  get_timeline       — Get visual timeline of session activity
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


def git_cmd(args, cwd):
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), 1


def get_repo_path(session_id):
    """Get repo/worktree path for a session."""
    meta_file = SESSIONS_DIR / session_id / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        return meta.get("worktree_path") or meta.get("repo_path")
    return None


def create_checkpoint(session_id, label, description=""):
    """Create a checkpoint (git commit + tag) for a session."""
    repo_path = get_repo_path(session_id)
    if not repo_path or not Path(repo_path).exists():
        return {"error": "No repo path found for session."}

    timestamp = int(time.time())
    tag_name = f"checkpoint/{session_id}/{timestamp}-{label}"

    # Stage all changes
    git_cmd(["add", "-A"], repo_path)

    # Check if there are changes to commit
    status, _ = git_cmd(["status", "--porcelain"], repo_path)
    if status.strip():
        # Commit changes
        commit_msg = f"checkpoint: {label}"
        if description:
            commit_msg += f"\n\n{description}"
        git_cmd(["commit", "-m", commit_msg, "--allow-empty"], repo_path)

    # Get current commit hash
    commit_hash, _ = git_cmd(["rev-parse", "HEAD"], repo_path)

    # Create tag
    tag_msg = f"Checkpoint: {label}\nSession: {session_id}\n{description}"
    git_cmd(["tag", "-a", tag_name, "-m", tag_msg], repo_path)

    # Save checkpoint metadata
    checkpoints_file = SESSIONS_DIR / session_id / "checkpoints.json"
    checkpoints = []
    if checkpoints_file.exists():
        checkpoints = json.loads(checkpoints_file.read_text())

    checkpoint = {
        "id": f"{timestamp}-{label}",
        "label": label,
        "description": description,
        "tag": tag_name,
        "commit": commit_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_changed": status.count("\n") + (1 if status.strip() else 0),
    }
    checkpoints.append(checkpoint)

    with open(checkpoints_file, "w") as f:
        json.dump(checkpoints, f, indent=2)

    return checkpoint


def list_checkpoints(session_id):
    """List all checkpoints for a session."""
    checkpoints_file = SESSIONS_DIR / session_id / "checkpoints.json"
    if not checkpoints_file.exists():
        return []
    return json.loads(checkpoints_file.read_text())


def rewind_to_checkpoint(session_id, checkpoint_id):
    """Rewind a session to a specific checkpoint."""
    repo_path = get_repo_path(session_id)
    if not repo_path:
        return {"error": "No repo path for session."}

    checkpoints = list_checkpoints(session_id)
    checkpoint = None
    for cp in checkpoints:
        if cp["id"] == checkpoint_id or cp["label"] == checkpoint_id:
            checkpoint = cp
            break

    if not checkpoint:
        return {"error": f"Checkpoint '{checkpoint_id}' not found."}

    # Create a rewind checkpoint first (so we can undo the rewind)
    create_checkpoint(session_id, f"pre-rewind-to-{checkpoint['label']}", "Auto-checkpoint before rewind")

    # Reset to the checkpoint commit
    output, code = git_cmd(["checkout", checkpoint["commit"], "--", "."], repo_path)
    if code != 0:
        return {"error": f"Git checkout failed: {output}"}

    # Commit the rewind
    git_cmd(["add", "-A"], repo_path)
    git_cmd(["commit", "-m", f"rewind: restored to checkpoint '{checkpoint['label']}'"], repo_path)

    return {
        "rewound_to": checkpoint,
        "status": "success",
        "message": f"Session rewound to checkpoint '{checkpoint['label']}' ({checkpoint['commit'][:8]})",
    }


def compare_checkpoints(session_id, from_id, to_id):
    """Compare two checkpoints."""
    repo_path = get_repo_path(session_id)
    if not repo_path:
        return {"error": "No repo path."}

    checkpoints = list_checkpoints(session_id)
    from_cp = None
    to_cp = None
    for cp in checkpoints:
        if cp["id"] == from_id or cp["label"] == from_id:
            from_cp = cp
        if cp["id"] == to_id or cp["label"] == to_id:
            to_cp = cp

    if not from_cp or not to_cp:
        return {"error": "Checkpoint(s) not found."}

    diff, _ = git_cmd(["diff", from_cp["commit"], to_cp["commit"], "--stat"], repo_path)
    return {
        "from": from_cp,
        "to": to_cp,
        "diff_stat": diff,
    }


def get_timeline(session_id, limit=20):
    """Get a visual timeline of session checkpoints and events."""
    checkpoints = list_checkpoints(session_id)

    # Also include events from black box
    events_file = SESSIONS_DIR / session_id / "events" / "black-box.jsonl"
    events = []
    if events_file.exists():
        for line in events_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Merge checkpoints and events into timeline
    timeline = []
    for cp in checkpoints:
        timeline.append({
            "time": cp["timestamp"],
            "type": "checkpoint",
            "label": cp["label"],
            "commit": cp["commit"][:8],
        })
    for ev in events[-50:]:
        timeline.append({
            "time": ev.get("timestamp", ""),
            "type": ev.get("type", "event"),
            "label": ev.get("type", "?"),
        })

    timeline.sort(key=lambda x: x.get("time", ""))
    return timeline[-limit:]


# --- MCP Tools ---

TOOLS = [
    {
        "name": "create_checkpoint",
        "description": "Create a checkpoint (git snapshot) before a risky operation. Can be rewound to later.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "label": {"type": "string", "description": "Short label (e.g., 'before-refactor', 'before-migration')."},
                "description": {"type": "string", "description": "Optional longer description."},
            },
            "required": ["session_id", "label"],
        },
    },
    {
        "name": "list_checkpoints",
        "description": "List all checkpoints for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    {
        "name": "rewind_to",
        "description": "Rewind a session to a specific checkpoint. Creates a safety checkpoint first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID or label to rewind to."},
            },
            "required": ["session_id", "checkpoint_id"],
        },
    },
    {
        "name": "compare_checkpoints",
        "description": "Show the diff between two checkpoints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "from_checkpoint": {"type": "string"},
                "to_checkpoint": {"type": "string"},
            },
            "required": ["session_id", "from_checkpoint", "to_checkpoint"],
        },
    },
    {
        "name": "get_timeline",
        "description": "Get a visual timeline of session activity and checkpoints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "description": "Max items (default 20)."},
            },
            "required": ["session_id"],
        },
    },
]


def handle_create_checkpoint(args):
    result = create_checkpoint(args["session_id"], args["label"], args.get("description", ""))
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": f"Checkpoint `{result['label']}` created at `{result['commit'][:8]}`."}]}


def handle_list_checkpoints(args):
    cps = list_checkpoints(args["session_id"])
    if not cps:
        return {"content": [{"type": "text", "text": "No checkpoints found."}]}
    lines = [f"## Checkpoints ({len(cps)})\n"]
    for cp in cps:
        lines.append(f"- `{cp['commit'][:8]}` **{cp['label']}** ({cp['timestamp'][11:19]}) — {cp.get('description', '')[:50]}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_rewind_to(args):
    result = rewind_to_checkpoint(args["session_id"], args["checkpoint_id"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": result["message"]}]}


def handle_compare_checkpoints(args):
    result = compare_checkpoints(args["session_id"], args["from_checkpoint"], args["to_checkpoint"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": f"## Diff: {args['from_checkpoint']} → {args['to_checkpoint']}\n```\n{result['diff_stat']}\n```"}]}


def handle_get_timeline(args):
    timeline = get_timeline(args["session_id"], args.get("limit", 20))
    if not timeline:
        return {"content": [{"type": "text", "text": "No timeline data."}]}
    lines = ["## Session Timeline\n"]
    for item in timeline:
        marker = "🔖" if item["type"] == "checkpoint" else "•"
        lines.append(f"{marker} `{item.get('time', '?')[11:19]}` **{item['type']}**: {item.get('label', '')}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


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
            "serverInfo": {"name": "timeline-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "create_checkpoint": handle_create_checkpoint,
            "list_checkpoints": handle_list_checkpoints,
            "rewind_to": handle_rewind_to,
            "compare_checkpoints": handle_compare_checkpoints,
            "get_timeline": handle_get_timeline,
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
            sys.stderr.write(f"Timeline MCP error: {e}\n")


if __name__ == "__main__":
    main()
