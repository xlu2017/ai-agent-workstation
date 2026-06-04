"""
Task Queue — manages autonomous task lifecycle.

States: queued → running → validating → committed | failed | needs_review
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.base import TaskPacket, TaskResult, SESSIONS_DIR, TASKS_DIR
from executors.direct_executor import DirectExecutor
from executors.aider_executor import AiderExecutor


SAFETY_POLICY = {
    "auto_commit": [
        "docs", "tests", "lint", "dead-code", "typo", "format",
        "comment", "readme", "changelog", "type-fix",
    ],
    "needs_review": [
        "logic", "validation", "api", "auth", "database",
        "migration", "dependency", "security", "config",
    ],
    "never_auto": [
        "secrets", "billing", "deploy", "destructive-migration",
        "license", "delete-directory", "production",
    ],
}


def classify_risk(instruction: str) -> str:
    """Classify task risk level based on instruction content."""
    instruction_lower = instruction.lower()

    for keyword in SAFETY_POLICY["never_auto"]:
        if keyword in instruction_lower:
            return "high"

    for keyword in SAFETY_POLICY["needs_review"]:
        if keyword in instruction_lower:
            return "medium"

    for keyword in SAFETY_POLICY["auto_commit"]:
        if keyword in instruction_lower:
            return "low"

    return "medium"


class TaskQueue:
    """Manages task lifecycle and executor dispatch."""

    def __init__(self):
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        self._executors = {
            "direct": DirectExecutor(),
            "openhands": DirectExecutor(),  # Direct is the primary executor
            "aider": AiderExecutor(),
        }
        self._running_tasks = {}
        self._lock = threading.Lock()

    def enqueue(self, packet: TaskPacket, executor: str = "openhands") -> str:
        """Add task to queue. Returns task_id."""
        packet.risk_level = classify_risk(packet.instruction)
        packet_path = packet.save()

        # Update status
        self._update_task_status(packet.task_id, "queued")

        # Start execution in background thread
        thread = threading.Thread(
            target=self._execute_task,
            args=(packet, executor),
            daemon=True,
        )
        thread.start()

        with self._lock:
            self._running_tasks[packet.task_id] = {
                "thread": thread,
                "status": "queued",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

        return packet.task_id

    def _execute_task(self, packet: TaskPacket, executor_name: str):
        """Execute task in background."""
        self._update_task_status(packet.task_id, "running")

        with self._lock:
            if packet.task_id in self._running_tasks:
                self._running_tasks[packet.task_id]["status"] = "running"

        executor = self._executors.get(executor_name)
        if not executor:
            self._update_task_status(packet.task_id, "failed", error=f"Unknown executor: {executor_name}")
            return

        try:
            result = executor.run_task(packet.session_id, packet)
        except Exception as e:
            self._update_task_status(packet.task_id, "failed", error=str(e))
            return

        # Apply safety policy
        if result.status == "committed" and packet.risk_level == "high":
            # High-risk tasks should never auto-commit
            result.status = "needs_review"

        self._update_task_status(
            packet.task_id, result.status,
            commit_sha=result.commit_sha,
            files_edited=result.files_edited,
            duration=result.duration_seconds,
            error=result.error,
        )

        # Save result
        result_path = TASKS_DIR / packet.task_id / "result.json"
        result_path.write_text(json.dumps({
            "status": result.status,
            "files_edited": result.files_edited,
            "commands_run": result.commands_run,
            "tests_passed": result.tests_passed,
            "tests_failed": result.tests_failed,
            "commit_sha": result.commit_sha,
            "error": result.error,
            "cost_usd": result.cost_usd,
            "duration_seconds": result.duration_seconds,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

        # Update messages.jsonl with result
        messages_file = SESSIONS_DIR / packet.session_id / "messages.jsonl"
        msg = {
            "role": "assistant",
            "content": self._format_result(result, packet),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": result.status,
            "task_id": packet.task_id,
            "files_edited": result.files_edited,
            "commit_sha": result.commit_sha,
        }
        with open(messages_file, "a") as f:
            f.write(json.dumps(msg) + "\n")

    def _format_result(self, result: TaskResult, packet: TaskPacket) -> str:
        """Format result for display in chat."""
        if result.status == "committed":
            parts = [f"Task completed and committed ({result.commit_sha[:8] if result.commit_sha else 'unknown'})."]
            if result.files_edited:
                parts.append(f"Files edited: {', '.join(result.files_edited[:5])}")
            if result.tests_passed:
                parts.append(f"Tests: {result.tests_passed} passed")
            parts.append(f"Duration: {result.duration_seconds:.1f}s")
            return "\n".join(parts)
        elif result.status == "failed":
            return f"Task failed: {result.error or 'unknown error'}\nDuration: {result.duration_seconds:.1f}s"
        elif result.status == "needs_review":
            parts = ["Task completed but needs review (risk level: {}).".format(packet.risk_level)]
            if result.files_edited:
                parts.append(f"Files edited: {', '.join(result.files_edited[:5])}")
            return "\n".join(parts)
        return f"Task status: {result.status}"

    def _update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task meta file with new status."""
        meta_path = TASKS_DIR / task_id / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            meta = {"task_id": task_id}
        meta["status"] = status
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        meta.update(kwargs)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2))

    def get_task_status(self, task_id: str) -> dict:
        """Get current task status."""
        meta_path = TASKS_DIR / task_id / "meta.json"
        if meta_path.exists():
            return json.loads(meta_path.read_text())
        return {"task_id": task_id, "status": "unknown"}

    def list_tasks(self, limit: int = 50) -> list:
        """List recent tasks."""
        tasks = []
        if TASKS_DIR.exists():
            for d in sorted(TASKS_DIR.iterdir(), reverse=True)[:limit]:
                meta_file = d / "meta.json"
                if meta_file.exists():
                    tasks.append(json.loads(meta_file.read_text()))
        return tasks
