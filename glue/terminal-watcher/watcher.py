#!/usr/bin/env python3
"""
Terminal Error Watcher — Captures failing commands and stack traces from tmux sessions.

Monitors tmux session panes for:
- Non-zero exit codes
- Stack traces (Python, Node.js, Rust, Go)
- Test failure summaries
- Build errors

Writes context to:
  /opt/workstation/sessions/<session_id>/context/latest-terminal-context.md
  /opt/workstation/sessions/<session_id>/events/terminal-events.jsonl

Can run as:
  1. Daemon: continuously polls all active tmux sessions
  2. Hook: triggered after each command via shell integration
  3. One-shot: capture current pane state
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
POLL_INTERVAL = 2  # seconds


# --- Stack Trace Parsers ---

PYTHON_TRACEBACK = re.compile(
    r'(Traceback \(most recent call last\):.*?)(?=\n\S|\Z)',
    re.DOTALL
)

PYTHON_ERROR_LINE = re.compile(
    r'^\s*File "([^"]+)", line (\d+), in (\S+)',
    re.MULTILINE
)

NODE_ERROR = re.compile(
    r'((?:TypeError|ReferenceError|SyntaxError|Error|RangeError|URIError):\s*.+?)(?=\n\s*$|\Z)',
    re.DOTALL
)

NODE_STACK_LINE = re.compile(
    r'^\s+at\s+(?:(.+?)\s+\()?(.+?):(\d+):(\d+)\)?',
    re.MULTILINE
)

RUST_ERROR = re.compile(
    r'(error\[E\d+\]:.+?)(?=\n\n|\Z)',
    re.DOTALL
)

RUST_LOCATION = re.compile(
    r'^\s*--> (.+?):(\d+):(\d+)',
    re.MULTILINE
)

GO_PANIC = re.compile(
    r'((?:panic:|runtime error:).+?)(?=\n\n|\Z)',
    re.DOTALL
)

GO_STACK_LINE = re.compile(
    r'^\s+(.+?):(\d+)',
    re.MULTILINE
)

PYTEST_FAILURE = re.compile(
    r'(FAILED .+?)(?=\n|$)',
    re.MULTILINE
)

JEST_FAILURE = re.compile(
    r'(FAIL .+?)(?=\n|$)',
    re.MULTILINE
)

EXIT_CODE_PATTERN = re.compile(r'exit (?:code|status):?\s*(\d+)', re.IGNORECASE)


def parse_stack_traces(output):
    """Extract stack traces and error info from terminal output."""
    errors = []

    # Python tracebacks
    for match in PYTHON_TRACEBACK.finditer(output):
        trace = match.group(0)
        files = PYTHON_ERROR_LINE.findall(trace)
        error_line = trace.strip().split('\n')[-1] if trace.strip() else ""
        errors.append({
            "language": "python",
            "type": "traceback",
            "message": error_line,
            "trace": trace.strip(),
            "files": [{"file": f[0], "line": int(f[1]), "function": f[2]} for f in files],
        })

    # Node.js errors
    for match in NODE_ERROR.finditer(output):
        trace = match.group(0)
        files = NODE_STACK_LINE.findall(trace)
        errors.append({
            "language": "node",
            "type": "error",
            "message": trace.split('\n')[0].strip(),
            "trace": trace.strip(),
            "files": [{"file": f[1], "line": int(f[2]), "column": int(f[3]), "function": f[0] or ""} for f in files],
        })

    # Rust errors
    for match in RUST_ERROR.finditer(output):
        trace = match.group(0)
        locations = RUST_LOCATION.findall(trace)
        errors.append({
            "language": "rust",
            "type": "compiler_error",
            "message": trace.split('\n')[0].strip(),
            "trace": trace.strip(),
            "files": [{"file": l[0], "line": int(l[1]), "column": int(l[2])} for l in locations],
        })

    # Go panics
    for match in GO_PANIC.finditer(output):
        trace = match.group(0)
        files = GO_STACK_LINE.findall(trace)
        errors.append({
            "language": "go",
            "type": "panic",
            "message": trace.split('\n')[0].strip(),
            "trace": trace.strip(),
            "files": [{"file": f[0], "line": int(f[1])} for f in files],
        })

    # Pytest failures
    for match in PYTEST_FAILURE.finditer(output):
        errors.append({
            "language": "python",
            "type": "test_failure",
            "message": match.group(0).strip(),
            "trace": "",
            "files": [],
        })

    # Jest failures
    for match in JEST_FAILURE.finditer(output):
        errors.append({
            "language": "node",
            "type": "test_failure",
            "message": match.group(0).strip(),
            "trace": "",
            "files": [],
        })

    return errors


def detect_last_command_failure(output):
    """Try to detect if the last command failed."""
    lines = output.strip().split('\n')
    if not lines:
        return None

    # Common failure indicators in last few lines
    tail = '\n'.join(lines[-20:])

    indicators = [
        (r'error:', 'error'),
        (r'Error:', 'error'),
        (r'FAILED', 'test_failure'),
        (r'FAIL ', 'test_failure'),
        (r'npm ERR!', 'npm_error'),
        (r'command not found', 'command_not_found'),
        (r'Permission denied', 'permission_denied'),
        (r'No such file', 'file_not_found'),
        (r'ModuleNotFoundError', 'import_error'),
        (r'ImportError', 'import_error'),
        (r'Cannot find module', 'import_error'),
        (r'compilation failed', 'build_error'),
        (r'Build failed', 'build_error'),
    ]

    for pattern, error_type in indicators:
        if re.search(pattern, tail):
            return error_type

    return None


def capture_tmux_pane(session_name, pane_id=None):
    """Capture content from a tmux pane."""
    target = f"{session_name}:{pane_id}" if pane_id else session_name
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p", "-S", "-100"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def get_tmux_sessions():
    """List all tmux sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return [s.strip() for s in result.stdout.strip().split('\n') if s.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def map_tmux_to_session(tmux_name):
    """Map tmux session name to workstation session ID."""
    for session_dir in SESSIONS_DIR.iterdir():
        meta_file = session_dir / "session.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                if meta.get("tmux_session") == tmux_name:
                    return session_dir.name, meta
            except (json.JSONDecodeError, OSError):
                continue

    # Fallback: strip "agent-" prefix
    if tmux_name.startswith("agent-"):
        candidate = tmux_name[6:]
        if (SESSIONS_DIR / candidate).exists():
            return candidate, {}

    return None, None


def write_terminal_context(session_id, event):
    """Write terminal context to session files."""
    base_dir = SESSIONS_DIR / session_id
    context_dir = base_dir / "context"
    events_dir = base_dir / "events"
    context_dir.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    # Append to JSONL
    jsonl_file = events_dir / "terminal-events.jsonl"
    with open(jsonl_file, "a") as f:
        f.write(json.dumps(event) + "\n")

    # Write markdown context
    md_file = context_dir / "latest-terminal-context.md"
    md_content = generate_terminal_md(event)
    with open(md_file, "w") as f:
        f.write(md_content)


def generate_terminal_md(event):
    """Generate agent-readable markdown from a terminal event."""
    lines = [
        "# Latest Terminal Context",
        "",
        f"**Timestamp:** {event.get('timestamp', 'unknown')}",
        f"**Session:** {event.get('session_id', 'unknown')}",
        f"**tmux:** {event.get('tmux_session', 'unknown')}",
        "",
    ]

    if event.get("command"):
        lines.extend([
            "## Last Command",
            f"```bash",
            event["command"],
            "```",
            "",
        ])

    if event.get("exit_code") is not None:
        lines.append(f"**Exit code:** {event['exit_code']}")
        lines.append("")

    errors = event.get("errors", [])
    if errors:
        lines.extend(["## Errors Detected", ""])
        for i, err in enumerate(errors, 1):
            lines.append(f"### Error {i}: {err.get('type', 'unknown')} ({err.get('language', '?')})")
            if err.get("message"):
                lines.append(f"**Message:** `{err['message']}`")
            if err.get("files"):
                lines.append("**Files:**")
                for f in err["files"][:5]:
                    loc = f"`{f['file']}:{f.get('line', '?')}`"
                    if f.get("function"):
                        loc += f" in `{f['function']}`"
                    lines.append(f"- {loc}")
            if err.get("trace"):
                lines.extend(["", "**Stack trace:**", "```", err["trace"][:2000], "```"])
            lines.append("")

    if event.get("output_tail"):
        lines.extend([
            "## Recent Output (last 30 lines)",
            "```",
            event["output_tail"],
            "```",
            "",
        ])

    lines.extend(["## Suggested Agent Action", ""])
    if errors:
        primary = errors[0]
        if primary.get("files"):
            f = primary["files"][0]
            lines.append(f"Open `{f['file']}` at line {f.get('line', '?')} and fix the {primary.get('type', 'error')}.")
        elif primary.get("message"):
            lines.append(f"Investigate: `{primary['message']}`")
        else:
            lines.append("Check the stack trace above and fix the error.")
    else:
        lines.append("Review the terminal output for context on what failed.")

    lines.append("")
    return "\n".join(lines)


def process_pane(tmux_session, session_id):
    """Process a single tmux pane for errors."""
    output = capture_tmux_pane(tmux_session)
    if not output.strip():
        return None

    errors = parse_stack_traces(output)
    failure_type = detect_last_command_failure(output)

    if not errors and not failure_type:
        return None

    # Extract last few lines for context
    output_lines = output.strip().split('\n')
    output_tail = '\n'.join(output_lines[-30:])

    event = {
        "type": "terminal_error",
        "session_id": session_id,
        "tmux_session": tmux_session,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_type": failure_type,
        "errors": errors,
        "output_tail": output_tail,
        "command": None,  # Filled by shell hook if available
        "exit_code": None,
    }

    return event


# --- Shell Hook Integration ---

def handle_shell_hook(session_id, command, exit_code, tmux_session=None):
    """Called by shell hook after each command completion."""
    if int(exit_code) == 0:
        return  # Only capture failures

    output = ""
    if tmux_session:
        output = capture_tmux_pane(tmux_session)

    errors = parse_stack_traces(output)
    output_lines = output.strip().split('\n') if output else []
    output_tail = '\n'.join(output_lines[-30:]) if output_lines else ""

    event = {
        "type": "terminal_error",
        "session_id": session_id,
        "tmux_session": tmux_session or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_type": "command_failed",
        "errors": errors,
        "output_tail": output_tail,
        "command": command,
        "exit_code": int(exit_code),
    }

    write_terminal_context(session_id, event)
    return event


# --- Daemon Mode ---

def daemon_loop():
    """Continuously poll tmux sessions for errors."""
    seen_hashes = {}

    print(f"Terminal watcher daemon started. Polling every {POLL_INTERVAL}s.")
    print(f"Sessions dir: {SESSIONS_DIR}")

    while True:
        try:
            tmux_sessions = get_tmux_sessions()
            for tmux_name in tmux_sessions:
                session_id, meta = map_tmux_to_session(tmux_name)
                if not session_id:
                    continue

                event = process_pane(tmux_name, session_id)
                if event:
                    # Deduplicate: hash the error to avoid spamming
                    error_hash = hash(json.dumps(event.get("errors", [])))
                    if seen_hashes.get(tmux_name) != error_hash:
                        seen_hashes[tmux_name] = error_hash
                        write_terminal_context(session_id, event)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error captured in {tmux_name} → {session_id}")

        except Exception as e:
            print(f"Watcher error: {e}", file=sys.stderr)

        time.sleep(POLL_INTERVAL)


# --- CLI ---

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  watcher.py daemon              — Poll all tmux sessions continuously")
        print("  watcher.py capture <tmux>      — One-shot capture from a tmux session")
        print("  watcher.py hook <session_id> <command> <exit_code> [tmux_session]")
        print("                                  — Shell hook after command failure")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "daemon":
        daemon_loop()

    elif cmd == "capture":
        if len(sys.argv) < 3:
            print("Usage: watcher.py capture <tmux_session_name>")
            sys.exit(1)
        tmux_name = sys.argv[2]
        session_id, meta = map_tmux_to_session(tmux_name)
        if not session_id:
            session_id = tmux_name
        event = process_pane(tmux_name, session_id)
        if event:
            write_terminal_context(session_id, event)
            print(json.dumps(event, indent=2))
        else:
            print("No errors detected in pane.")

    elif cmd == "hook":
        if len(sys.argv) < 5:
            print("Usage: watcher.py hook <session_id> <command> <exit_code> [tmux_session]")
            sys.exit(1)
        session_id = sys.argv[2]
        command = sys.argv[3]
        exit_code = sys.argv[4]
        tmux_session = sys.argv[5] if len(sys.argv) > 5 else None
        event = handle_shell_hook(session_id, command, exit_code, tmux_session)
        if event:
            print(json.dumps(event, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
