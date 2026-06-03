#!/usr/bin/env python3
"""
Session Timeline — Records every action in a session for observability.

Events:
- context_received: UI/editor/terminal context event routed to session
- file_read: Agent read a file
- file_edited: Agent modified a file
- command_run: Agent ran a shell command
- test_result: Test pass/fail with output
- model_call: LLM API call with model, tokens, cost
- checkpoint: Git checkpoint created
- build_result: Build pass/fail
- error: Any error encountered
- branch_ready: Branch is PR-ready

Storage: /opt/workstation/sessions/<id>/timeline.jsonl
Summary: /opt/workstation/sessions/<id>/timeline-summary.md
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))

# Cost per 1M tokens (approximate)
MODEL_COSTS = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-coder": {"input": 0.14, "output": 0.28},
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "qwen-plus": {"input": 0.80, "output": 2.40},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


class Timeline:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = SESSIONS_DIR / session_id
        self.timeline_file = self.session_dir / "timeline.jsonl"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, data: dict = None) -> dict:
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            **(data or {}),
        }
        with open(self.timeline_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def record_context(self, context_type: str, source: str, summary: str):
        return self.record("context_received", {
            "context_type": context_type,
            "source": source,
            "summary": summary,
        })

    def record_file_read(self, file_path: str, lines: int = 0):
        return self.record("file_read", {"file": file_path, "lines": lines})

    def record_file_edit(self, file_path: str, diff_summary: str = ""):
        return self.record("file_edited", {"file": file_path, "diff": diff_summary})

    def record_command(self, command: str, exit_code: int, output_preview: str = ""):
        return self.record("command_run", {
            "command": command,
            "exit_code": exit_code,
            "output": output_preview[:500],
        })

    def record_test(self, test_name: str, passed: bool, output: str = "", duration_ms: int = 0):
        return self.record("test_result", {
            "test": test_name,
            "passed": passed,
            "output": output[:500],
            "duration_ms": duration_ms,
        })

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int, purpose: str = ""):
        cost = self._estimate_cost(model, input_tokens, output_tokens)
        return self.record("model_call", {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "purpose": purpose,
        })

    def record_build(self, passed: bool, output: str = "", duration_ms: int = 0):
        return self.record("build_result", {
            "passed": passed,
            "output": output[:500],
            "duration_ms": duration_ms,
        })

    def record_error(self, error_type: str, message: str, file_path: str = ""):
        return self.record("error", {
            "error_type": error_type,
            "message": message[:500],
            "file": file_path,
        })

    def record_branch_ready(self, branch: str, commit: str, files_changed: int):
        return self.record("branch_ready", {
            "branch": branch,
            "commit": commit,
            "files_changed": files_changed,
        })

    def get_events(self, limit: int = 100, event_type: str = None) -> list:
        if not self.timeline_file.exists():
            return []
        events = []
        for line in self.timeline_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    ev = json.loads(line)
                    if event_type is None or ev.get("type") == event_type:
                        events.append(ev)
                except json.JSONDecodeError:
                    continue
        return events[-limit:]

    def get_summary(self) -> dict:
        events = self.get_events(limit=10000)
        if not events:
            return {"session_id": self.session_id, "status": "empty", "events": 0}

        total_cost = sum(e.get("cost_usd", 0) for e in events if e.get("type") == "model_call")
        files_read = set(e.get("file", "") for e in events if e.get("type") == "file_read")
        files_edited = set(e.get("file", "") for e in events if e.get("type") == "file_edited")
        commands = [e for e in events if e.get("type") == "command_run"]
        tests = [e for e in events if e.get("type") == "test_result"]
        errors = [e for e in events if e.get("type") == "error"]
        model_calls = [e for e in events if e.get("type") == "model_call"]

        tests_passed = sum(1 for t in tests if t.get("passed"))
        tests_failed = sum(1 for t in tests if not t.get("passed"))

        return {
            "session_id": self.session_id,
            "total_events": len(events),
            "duration_seconds": self._calc_duration(events),
            "cost_usd": round(total_cost, 4),
            "files_read": len(files_read),
            "files_edited": len(files_edited),
            "commands_run": len(commands),
            "model_calls": len(model_calls),
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "errors": len(errors),
            "first_event": events[0].get("timestamp", "") if events else "",
            "last_event": events[-1].get("timestamp", "") if events else "",
            "models_used": list(set(e.get("model", "") for e in model_calls)),
        }

    def generate_markdown(self) -> str:
        """Generate human-readable timeline markdown."""
        events = self.get_events(limit=10000)
        summary = self.get_summary()

        lines = [
            f"# Session Timeline: {self.session_id}",
            "",
            f"**Duration:** {summary.get('duration_seconds', 0)//60}m {summary.get('duration_seconds', 0)%60}s",
            f"**Cost:** ${summary.get('cost_usd', 0):.4f}",
            f"**Files read:** {summary.get('files_read', 0)} | **Files edited:** {summary.get('files_edited', 0)}",
            f"**Commands:** {summary.get('commands_run', 0)} | **Model calls:** {summary.get('model_calls', 0)}",
            f"**Tests:** {summary.get('tests_passed', 0)} passed, {summary.get('tests_failed', 0)} failed",
            f"**Errors:** {summary.get('errors', 0)}",
            "",
            "## Event Log",
            "",
        ]

        for ev in events:
            ts = ev.get("timestamp", "")[11:19]  # HH:MM:SS
            etype = ev.get("type", "?")
            detail = self._event_one_liner(ev)
            lines.append(f"- `{ts}` **{etype}** {detail}")

        md = "\n".join(lines)
        summary_file = self.session_dir / "timeline-summary.md"
        summary_file.write_text(md)
        return md

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        model_key = model.lower().replace("/", "-")
        for key, costs in MODEL_COSTS.items():
            if key in model_key:
                return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000
        # Default to cheap model pricing
        return (input_tokens * 0.14 + output_tokens * 0.28) / 1_000_000

    def _calc_duration(self, events: list) -> int:
        if len(events) < 2:
            return 0
        try:
            first = datetime.fromisoformat(events[0]["timestamp"].replace("Z", "+00:00"))
            last = datetime.fromisoformat(events[-1]["timestamp"].replace("Z", "+00:00"))
            return int((last - first).total_seconds())
        except (ValueError, KeyError):
            return 0

    def _event_one_liner(self, ev: dict) -> str:
        etype = ev.get("type", "")
        if etype == "context_received":
            return f"`{ev.get('context_type', '?')}` from {ev.get('source', '?')}: {ev.get('summary', '')[:60]}"
        elif etype == "file_read":
            return f"`{ev.get('file', '?')}`"
        elif etype == "file_edited":
            return f"`{ev.get('file', '?')}` — {ev.get('diff', '')[:40]}"
        elif etype == "command_run":
            cmd = ev.get("command", "")[:50]
            code = ev.get("exit_code", "?")
            return f"`{cmd}` → exit {code}"
        elif etype == "test_result":
            status = "PASS" if ev.get("passed") else "FAIL"
            return f"{status} `{ev.get('test', '?')}`"
        elif etype == "model_call":
            return f"`{ev.get('model', '?')}` {ev.get('input_tokens', 0)}→{ev.get('output_tokens', 0)} tok (${ev.get('cost_usd', 0):.4f})"
        elif etype == "build_result":
            return "PASS" if ev.get("passed") else f"FAIL: {ev.get('output', '')[:40]}"
        elif etype == "error":
            return f"`{ev.get('error_type', '?')}` {ev.get('message', '')[:60]}"
        elif etype == "branch_ready":
            return f"`{ev.get('branch', '?')}` @ {ev.get('commit', '?')[:8]} ({ev.get('files_changed', 0)} files)"
        return json.dumps(ev)[:60]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 timeline.py <session_id> [summary|markdown|events]")
        sys.exit(1)

    session_id = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "summary"
    tl = Timeline(session_id)

    if action == "summary":
        print(json.dumps(tl.get_summary(), indent=2))
    elif action == "markdown":
        print(tl.generate_markdown())
    elif action == "events":
        for ev in tl.get_events():
            print(json.dumps(ev))
    else:
        print(f"Unknown action: {action}")
