"""
Workflow transcript aggregation.

Builds a compact, user-visible workflow transcript from raw session events.
Separates execution telemetry (reads, searches, edits, commands, tests,
elapsed thinking gaps) from hidden reasoning text.

The transcript is the single source of truth for what the UI renders in the
worklog/chat timeline.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def build_workflow_transcript(
    session_id: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an aggregated workflow transcript from raw session events.

    Returns a dict suitable for JSON serialization and UI rendering:
    {
        "session_id": "...",
        "headline": "Investigating ...",
        "working_duration_ms": 156000,
        "additions": 30,
        "deletions": 3,
        "tasks_created": 3,
        "items": [ ... ],
        "validation": { "overall": "passed", "commands": [] },
    }
    """
    items: list[dict[str, Any]] = []
    tasks_created = 0
    total_additions = 0
    total_deletions = 0
    headline = ""
    first_action_ts: str | None = None
    last_completed_ts: str | None = None
    validation_commands: list[dict[str, Any]] = []
    validation_overall = "not_run"
    prev_ts: str | None = None

    for ev in events:
        et = ev.get("event_type", "")
        d = ev.get("data", {})
        ts = ev.get("timestamp", "")
        msg = d.get("message", "")

        # Track thought gaps (>3s between events during execution)
        if prev_ts and first_action_ts and et not in (
            "user_prompt_received", "routing_decision_made",
        ):
            gap_ms = _ts_diff_ms(prev_ts, ts)
            if gap_ms > 3000:
                items.append({
                    "kind": "thought",
                    "label": f"Thought for {_format_elapsed(gap_ms)}",
                    "status": "completed",
                    "timestamp": ts,
                    "duration_ms": gap_ms,
                    "metadata": {},
                })
        prev_ts = ts

        if et == "routing_decision_made":
            if not headline:
                headline = msg

        elif et == "task_started":
            if not headline:
                headline = msg
            items.append({
                "kind": "status",
                "label": msg,
                "status": "completed",
                "timestamp": ts,
                "duration_ms": 0,
                "metadata": {},
            })

        elif et == "task_created":
            tasks_created += d.get("count", 1)
            task_titles = d.get("tasks", [])
            items.append({
                "kind": "tasks_created",
                "label": f"Created {d.get('count', 1)} Tasks",
                "status": "completed",
                "timestamp": ts,
                "duration_ms": 0,
                "metadata": {"tasks": task_titles},
            })

        elif et == "action_started":
            if not first_action_ts:
                first_action_ts = ts

        elif et == "file_read":
            path = d.get("path", "")
            fname = path.rsplit("/", 1)[-1] if "/" in path else path
            line_start = d.get("line_start")
            line_end = d.get("line_end")
            label = f"Read {fname}"
            if line_start is not None and line_end is not None:
                label += f":{line_start}-{line_end}"
            items.append({
                "kind": "read",
                "label": label,
                "status": "completed",
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": {"path": path, "line_start": line_start, "line_end": line_end},
            })

        elif et == "code_searched":
            query = d.get("query", "")
            path = d.get("path", "")
            fname = path.rsplit("/", 1)[-1] if "/" in path else (path or "codebase")
            result_count = d.get("result_count", 0)
            label = f"Searched {fname} for {query}"
            if result_count:
                label += f" ({result_count} results)"
            items.append({
                "kind": "search",
                "label": label,
                "status": "completed",
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": {"query": query, "path": path, "result_count": result_count},
            })

        elif et == "file_edited":
            path = d.get("path", "")
            fname = path.rsplit("/", 1)[-1] if "/" in path else path
            adds = d.get("additions", 0)
            dels = d.get("deletions", 0)
            total_additions += adds
            total_deletions += dels
            label = f"Edited {fname}"
            if adds or dels:
                label += f" +{adds} -{dels}"
            items.append({
                "kind": "edit",
                "label": label,
                "status": "completed",
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": {"path": path, "additions": adds, "deletions": dels},
            })

        elif et == "command_run":
            cmd = d.get("command", "")
            exit_code = d.get("exit_code")
            status = "completed" if exit_code == 0 or exit_code is None else "failed"
            label = f"Ran {_truncate(cmd, 60)}"
            items.append({
                "kind": "command",
                "label": label,
                "status": status,
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": {"command": cmd, "exit_code": exit_code},
            })

        elif et == "test_run":
            cmd = d.get("command", "")
            exit_code = d.get("exit_code")
            passed = d.get("tests_passed", 0)
            failed = d.get("tests_failed", 0)
            status = "completed" if exit_code == 0 or exit_code is None else "failed"
            label = f"Ran tests"
            if passed or failed:
                label += f" ({passed} passed, {failed} failed)"
            items.append({
                "kind": "test",
                "label": label,
                "status": status,
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": {"command": cmd, "exit_code": exit_code, "passed": passed, "failed": failed},
            })
            validation_commands.append({
                "command": cmd,
                "exit_code": exit_code,
                "status": status,
            })

        elif et == "thought_elapsed":
            duration_ms = d.get("duration_ms", 0)
            items.append({
                "kind": "thought",
                "label": f"Thought for {_format_elapsed(duration_ms)}",
                "status": "completed",
                "timestamp": ts,
                "duration_ms": duration_ms,
                "metadata": {},
            })

        elif et == "validation_completed":
            val_status = d.get("status", "not_run")
            validation_overall = val_status
            validation_commands.extend(d.get("commands", []))
            items.append({
                "kind": "validation",
                "label": f"Validation: {val_status}",
                "status": "completed" if val_status == "passed" else "failed",
                "timestamp": ts,
                "duration_ms": d.get("duration_ms", 0),
                "metadata": d,
            })

        elif et == "diff_summarized":
            adds = d.get("additions", 0)
            dels = d.get("deletions", 0)
            items.append({
                "kind": "diff",
                "label": f"Diff: +{adds} -{dels}",
                "status": "completed",
                "timestamp": ts,
                "duration_ms": 0,
                "metadata": d,
            })

        elif et == "task_completed" or et == "action_completed":
            last_completed_ts = ts

        elif et == "task_cancelled":
            items.append({
                "kind": "cancelled",
                "label": msg or "Task cancelled",
                "status": "cancelled",
                "timestamp": ts,
                "duration_ms": 0,
                "metadata": d,
            })

        # Legacy action_progress events: translate to granular types
        elif et == "action_progress":
            tool = d.get("tool", "")
            args_summary = d.get("args_summary", "")
            if tool in ("read_file", "str_replace_editor") and "view" in args_summary:
                path = _extract_path(args_summary)
                fname = path.rsplit("/", 1)[-1] if "/" in path else path
                ranges = _extract_range(args_summary)
                label = f"Read {fname}"
                if ranges:
                    label += f":{ranges}"
                items.append({
                    "kind": "read",
                    "label": label,
                    "status": "completed",
                    "timestamp": ts,
                    "duration_ms": 0,
                    "metadata": {"path": path},
                })
            elif tool in ("str_replace_editor", "write_file", "edit_file"):
                path = _extract_path(args_summary)
                fname = path.rsplit("/", 1)[-1] if "/" in path else path
                items.append({
                    "kind": "edit",
                    "label": f"Edited {fname}",
                    "status": "completed",
                    "timestamp": ts,
                    "duration_ms": 0,
                    "metadata": {"path": path},
                })
            elif tool in ("search", "grep", "find"):
                items.append({
                    "kind": "search",
                    "label": f"Searched {args_summary or 'codebase'}",
                    "status": "completed",
                    "timestamp": ts,
                    "duration_ms": 0,
                    "metadata": {},
                })
            elif tool in ("bash", "execute_bash"):
                cmd = d.get("command", args_summary or msg)
                items.append({
                    "kind": "command",
                    "label": f"Ran {_truncate(cmd, 60)}",
                    "status": "completed",
                    "timestamp": ts,
                    "duration_ms": 0,
                    "metadata": {"command": cmd},
                })

    # Compute working duration
    working_duration_ms = 0
    if first_action_ts and last_completed_ts:
        working_duration_ms = _ts_diff_ms(first_action_ts, last_completed_ts)

    # Derive validation overall from commands if not explicitly set
    if validation_overall == "not_run" and validation_commands:
        has_fail = any(c.get("status") == "failed" for c in validation_commands)
        has_pass = any(c.get("status") == "completed" for c in validation_commands)
        if has_fail and has_pass:
            validation_overall = "partial"
        elif has_fail:
            validation_overall = "failed"
        elif has_pass:
            validation_overall = "passed"

    return {
        "session_id": session_id,
        "headline": headline,
        "working_duration_ms": working_duration_ms,
        "additions": total_additions,
        "deletions": total_deletions,
        "tasks_created": tasks_created,
        "items": items,
        "validation": {
            "overall": validation_overall,
            "commands": validation_commands,
        },
    }


def generate_status_message(
    instruction: str,
    task_class: str = "",
    direct_action: str = "",
) -> str:
    """Generate a user-facing status message at task start.

    For code-fix prompts: "Investigating [bug summary] — looking at [subsystem] now."
    For direct actions: brief confirmation.
    For generic prompts: safe fallback.
    """
    instruction_lower = instruction.lower()

    if direct_action:
        action_labels = {
            "open_terminal": "Opening terminal on desktop.",
            "open_browser": "Opening browser on desktop.",
            "open_file_manager": "Opening file manager on desktop.",
        }
        return action_labels.get(direct_action, f"Executing {direct_action}.")

    if task_class == "desktop_control":
        return "Executing desktop action now."

    # Code-fix / bug-fix detection
    bug_keywords = ["fix", "bug", "broken", "doesn't work", "not working", "debug", "issue"]
    is_bugfix = any(kw in instruction_lower for kw in bug_keywords)

    if is_bugfix:
        # Extract a concise bug summary from the instruction
        summary = _extract_bug_summary(instruction)
        subsystem = _guess_subsystem(instruction)
        if subsystem:
            return f"Investigating {summary} — looking at {subsystem} now."
        return f"Investigating {summary}. I'll inspect the relevant code, apply a targeted fix, and validate it."

    # Implementation tasks
    impl_keywords = ["add", "implement", "create", "build", "wire"]
    is_impl = any(kw in instruction_lower for kw in impl_keywords)
    if is_impl:
        return f"Working on this now. I'll plan the implementation, make the changes, and validate."

    return "Processing your request now."


def generate_task_decomposition(
    instruction: str,
    task_class: str = "",
) -> list[dict[str, str]]:
    """Generate a compact task checklist (2-5 tasks) for code-fix prompts.

    Returns list of {"title": "...", "description": "..."} dicts.
    """
    instruction_lower = instruction.lower()

    bug_keywords = ["fix", "bug", "broken", "doesn't work", "not working", "debug", "issue"]
    is_bugfix = any(kw in instruction_lower for kw in bug_keywords)

    if is_bugfix:
        subsystem = _guess_subsystem(instruction)
        target = subsystem or "the relevant code"
        return [
            {"title": f"Trace the issue in {target}", "description": "Read and understand the current behavior."},
            {"title": "Identify the root cause", "description": "Search for the specific bug pattern."},
            {"title": "Apply a targeted fix", "description": "Edit only what's necessary to resolve the issue."},
            {"title": "Validate the fix", "description": "Run targeted tests or compile checks."},
        ]

    impl_keywords = ["add", "implement", "create", "build"]
    is_impl = any(kw in instruction_lower for kw in impl_keywords)
    if is_impl:
        return [
            {"title": "Understand requirements", "description": "Read existing code and interfaces."},
            {"title": "Implement changes", "description": "Write the new code."},
            {"title": "Validate", "description": "Run tests and compile checks."},
        ]

    return [
        {"title": "Investigate", "description": "Understand the current state."},
        {"title": "Execute", "description": "Make the required changes."},
        {"title": "Validate", "description": "Verify correctness."},
    ]


# --- Internal helpers ---

def _ts_diff_ms(ts1: str, ts2: str) -> int:
    """Milliseconds between two ISO timestamps."""
    try:
        t1 = datetime.fromisoformat(ts1.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(ts2.replace("Z", "+00:00"))
        return max(0, int((t2 - t1).total_seconds() * 1000))
    except (ValueError, TypeError):
        return 0


def _format_elapsed(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{int(secs)}s"
    mins = int(secs // 60)
    remaining_secs = int(secs % 60)
    return f"{mins}m {remaining_secs}s"


def _truncate(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _extract_path(args_summary: str) -> str:
    """Extract file path from tool args summary."""
    m = re.search(r'path[=:]\s*["\']?([^\s"\',:]+)', args_summary)
    if m:
        return m.group(1)
    m = re.search(r'([^\s,]+\.\w{1,6})', args_summary)
    if m:
        return m.group(1)
    return args_summary[:60]


def _extract_range(args_summary: str) -> str:
    """Extract line range from args summary."""
    m = re.search(r'(\d+)-(\d+)', args_summary)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _extract_bug_summary(instruction: str) -> str:
    """Extract a concise bug summary from user instruction."""
    # Remove common prefixes
    text = re.sub(r'^(fix|debug|resolve|investigate)\s+(the\s+)?(bug|issue|problem)?\s*(that|where|when|:)?\s*', '', instruction, flags=re.IGNORECASE).strip()
    if len(text) > 80:
        text = text[:77] + "..."
    return text or "the reported issue"


def _guess_subsystem(instruction: str) -> str:
    """Guess the subsystem from instruction keywords."""
    instruction_lower = instruction.lower()
    subsystem_hints = {
        "stop": "the stop/cancel flow",
        "cancel": "the cancellation system",
        "resume": "the task resume logic",
        "executor": "the executor",
        "terminal": "the terminal launcher",
        "desktop": "the desktop actions",
        "drag": "the resize handler",
        "iframe": "the iframe container",
        "session": "the session controller",
        "router": "the prompt router",
        "commit": "the commit flow",
        "worktree": "the worktree manager",
        "api": "the API layer",
        "ui": "the frontend",
        "worklog": "the worklog",
        "timeline": "the timeline",
    }
    for keyword, subsystem in subsystem_hints.items():
        if keyword in instruction_lower:
            return subsystem
    return ""
