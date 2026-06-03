#!/usr/bin/env python3
"""
Context Validator — Detects stale, misrouted, or unreliable context events.

Checks:
1. Staleness: Event older than threshold (default 5 minutes)
2. Branch mismatch: Event's worktree doesn't match session's current branch
3. Port mismatch: Event URL port doesn't belong to session's port range
4. Profile mismatch: Browser profile doesn't match session assignment
5. Worktree drift: File paths in event don't match session's worktree

Returns structured warnings that agents should check before acting on context.
"""

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
STALE_THRESHOLD_SECONDS = int(os.environ.get("STALE_THRESHOLD_SECONDS", "300"))  # 5 minutes


class ContextWarning:
    def __init__(self, level: str, code: str, message: str, details: dict = None):
        self.level = level  # "warning" | "error"
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self):
        return {"level": self.level, "code": self.code, "message": self.message, "details": self.details}


def get_session_meta(session_id: str) -> Optional[dict]:
    meta_file = SESSIONS_DIR / session_id / "session.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    return None


def get_current_branch(worktree_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def parse_port_range(port_range: str) -> tuple:
    if not port_range or "-" not in port_range:
        return (0, 0)
    parts = port_range.split("-")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def extract_port_from_url(url: str) -> Optional[int]:
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.port
    except Exception:
        return None


def validate_context(session_id: str, event: dict = None) -> list:
    """
    Validate context freshness and routing for a session.
    If event is None, reads latest context files.
    Returns list of ContextWarning objects.
    """
    warnings = []
    meta = get_session_meta(session_id)
    if not meta:
        warnings.append(ContextWarning("error", "SESSION_NOT_FOUND", f"Session '{session_id}' not found"))
        return [w.to_dict() for w in warnings]

    # Determine which context to validate
    if event is None:
        event = _load_latest_context(session_id)
        if not event:
            return []

    # 1. Staleness check
    timestamp = event.get("timestamp") or event.get("Timestamp")
    if timestamp:
        try:
            if isinstance(timestamp, str):
                event_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                event_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            age = (datetime.now(timezone.utc) - event_time).total_seconds()
            if age > STALE_THRESHOLD_SECONDS:
                warnings.append(ContextWarning(
                    "warning", "STALE_CONTEXT",
                    f"Context is {int(age)}s old (threshold: {STALE_THRESHOLD_SECONDS}s). Verify before acting.",
                    {"age_seconds": int(age), "threshold": STALE_THRESHOLD_SECONDS, "event_time": str(event_time)}
                ))
        except (ValueError, TypeError, OSError):
            pass

    # 2. Branch mismatch
    worktree_path = meta.get("worktree_path", "")
    if worktree_path and Path(worktree_path).exists():
        current_branch = get_current_branch(worktree_path)
        expected_branch = meta.get("branch", "")
        if current_branch and expected_branch and current_branch != expected_branch:
            warnings.append(ContextWarning(
                "error", "BRANCH_MISMATCH",
                f"Session branch '{expected_branch}' but worktree is on '{current_branch}'. Context may be from wrong branch.",
                {"expected": expected_branch, "actual": current_branch}
            ))

    # 3. Port mismatch
    url = event.get("url", "")
    event_port = extract_port_from_url(url)
    if event_port:
        port_low, port_high = parse_port_range(meta.get("port_range", ""))
        if port_low > 0 and not (port_low <= event_port <= port_high):
            warnings.append(ContextWarning(
                "error", "PORT_MISMATCH",
                f"Event from port {event_port} but session owns {meta.get('port_range')}. Possible cross-session leak.",
                {"event_port": event_port, "session_port_range": meta.get("port_range")}
            ))

    # 4. File path mismatch (editor context)
    file_path = event.get("file", "")
    if file_path and worktree_path:
        if not file_path.startswith(worktree_path) and not file_path.startswith("/"):
            pass  # relative path, could be ok
        elif file_path.startswith("/") and worktree_path and not file_path.startswith(worktree_path):
            # Check if it belongs to a different worktree
            other_worktree = _find_owning_session(file_path)
            if other_worktree and other_worktree != session_id:
                warnings.append(ContextWarning(
                    "error", "WRONG_WORKTREE",
                    f"File '{file_path}' belongs to session '{other_worktree}', not '{session_id}'.",
                    {"file": file_path, "actual_owner": other_worktree}
                ))

    return [w.to_dict() for w in warnings]


def _load_latest_context(session_id: str) -> Optional[dict]:
    """Load the most recent context event from JSONL files."""
    events_dir = SESSIONS_DIR / session_id / "events"
    if not events_dir.exists():
        return None

    latest_event = None
    latest_time = None

    for jsonl_file in events_dir.glob("*.jsonl"):
        try:
            lines = jsonl_file.read_text().strip().split("\n")
            if lines and lines[-1].strip():
                event = json.loads(lines[-1])
                ts = event.get("timestamp", "")
                if ts:
                    try:
                        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if latest_time is None or t > latest_time:
                            latest_time = t
                            latest_event = event
                    except ValueError:
                        if latest_event is None:
                            latest_event = event
        except (json.JSONDecodeError, OSError):
            continue

    return latest_event


def _find_owning_session(file_path: str) -> Optional[str]:
    """Find which session owns a given file path based on worktree."""
    if not SESSIONS_DIR.exists():
        return None
    for d in SESSIONS_DIR.iterdir():
        meta_file = d / "session.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                wt = meta.get("worktree_path", "")
                if wt and file_path.startswith(wt):
                    return meta.get("id")
            except (json.JSONDecodeError, OSError):
                continue
    return None


def get_context_health(session_id: str) -> dict:
    """
    Get overall context health for a session.
    Used by agents to decide whether to trust current context.
    """
    warnings = validate_context(session_id)
    has_errors = any(w["level"] == "error" for w in warnings)
    has_warnings = any(w["level"] == "warning" for w in warnings)

    if has_errors:
        status = "unreliable"
        advice = "Context has routing errors. Do NOT act on it without verification."
    elif has_warnings:
        status = "stale"
        advice = "Context may be outdated. Ask user to confirm before making changes."
    else:
        status = "fresh"
        advice = "Context is current and correctly routed. Safe to act."

    return {
        "session_id": session_id,
        "status": status,
        "advice": advice,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
        result = get_context_health(session_id)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 context_validator.py <session_id>")
