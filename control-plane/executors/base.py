"""
ExecutorAdapter — abstract interface for autonomous task execution.

Every executor must support:
- run_task(session_id, task_packet_path) → start execution
- stream_events(session_id) → yield JSONL events
- collect_diff(session_id) → return git diff
- run_validation(session_id) → run tests/lint/build
- commit_changes(session_id, message) → git commit on session branch
"""

import json
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


SESSIONS_DIR = Path("/opt/workstation/sessions")
TASKS_DIR = Path("/opt/workstation/tasks")


@dataclass
class TaskResult:
    status: str  # completed, failed, needs_review
    files_edited: list = field(default_factory=list)
    commands_run: list = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    commit_sha: Optional[str] = None
    error: Optional[str] = None
    summary: str = ""
    cost_usd: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class TaskPacket:
    task_id: str
    session_id: str
    instruction: str
    worktree_path: str
    branch: str
    ui_context: Optional[str] = None
    editor_context: Optional[str] = None
    terminal_context: Optional[str] = None
    activated_knowledge: list = field(default_factory=list)
    staleness_warnings: list = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high
    model: str = "deepseek-v4-flash"

    def to_markdown(self) -> str:
        parts = []
        parts.append(f"## Task\n{self.instruction}")
        if self.ui_context:
            parts.append(f"## UI Context (what user is looking at)\n{self.ui_context}")
        if self.editor_context:
            parts.append(f"## Editor Context (active file/selection)\n{self.editor_context}")
        if self.terminal_context:
            parts.append(f"## Terminal Context (recent error)\n{self.terminal_context}")
        if self.activated_knowledge:
            knowledge_text = "\n".join(
                f"- {k.get('description', '')}: {k.get('content', '')}"
                for k in self.activated_knowledge
            )
            parts.append(f"## Activated Knowledge\n{knowledge_text}")
        if self.staleness_warnings:
            warnings_text = "\n".join(f"- {w}" for w in self.staleness_warnings)
            parts.append(f"## Warnings\n{warnings_text}")
        parts.append(f"## Working Directory\n{self.worktree_path}")
        parts.append(f"## Branch\n{self.branch}")
        parts.append("\n## Rules\n- Edit only this worktree.\n- Run tests if available.\n- Commit changes to the session branch.\n- Do not touch main.")
        return "\n\n".join(parts)

    def save(self) -> Path:
        task_dir = TASKS_DIR / self.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        packet_path = task_dir / "task-packet.md"
        packet_path.write_text(self.to_markdown())
        meta_path = task_dir / "meta.json"
        meta_path.write_text(json.dumps({
            "task_id": self.task_id,
            "session_id": self.session_id,
            "instruction": self.instruction,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "risk_level": self.risk_level,
            "model": self.model,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        return packet_path


class ExecutorAdapter(ABC):
    """Abstract base for task executors."""

    @abstractmethod
    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        """Execute the task. Blocks until completion."""
        ...

    @abstractmethod
    def stream_events(self, session_id: str) -> Iterator[dict]:
        """Yield JSONL events as they occur."""
        ...

    def collect_diff(self, session_id: str) -> str:
        """Return git diff for the session worktree."""
        session_dir = SESSIONS_DIR / session_id
        meta = json.loads((session_dir / "session.json").read_text())
        worktree = meta.get("worktree_path", "")
        if not worktree or not Path(worktree).exists():
            return ""
        result = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=worktree, capture_output=True, text=True,
        )
        if not result.stdout.strip():
            result = subprocess.run(
                ["git", "diff"],
                cwd=worktree, capture_output=True, text=True,
            )
        return result.stdout

    def run_validation(self, session_id: str) -> dict:
        """Run tests/lint/build in the session worktree."""
        session_dir = SESSIONS_DIR / session_id
        meta = json.loads((session_dir / "session.json").read_text())
        worktree = meta.get("worktree_path", "")
        if not worktree or not Path(worktree).exists():
            return {"status": "skipped", "reason": "no worktree"}

        results = {"build": None, "lint": None, "test": None}
        pkg_json = Path(worktree) / "package.json"

        if pkg_json.exists():
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})

            if "build" in scripts:
                r = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=worktree, capture_output=True, text=True, timeout=120,
                )
                results["build"] = {"passed": r.returncode == 0, "output": r.stdout[-500:] + r.stderr[-500:]}

            if "lint" in scripts:
                r = subprocess.run(
                    ["npm", "run", "lint"],
                    cwd=worktree, capture_output=True, text=True, timeout=60,
                )
                results["lint"] = {"passed": r.returncode == 0, "output": r.stdout[-500:] + r.stderr[-500:]}

            if "test" in scripts:
                r = subprocess.run(
                    ["npm", "run", "test", "--", "--passWithNoTests"],
                    cwd=worktree, capture_output=True, text=True, timeout=120,
                )
                results["test"] = {"passed": r.returncode == 0, "output": r.stdout[-500:] + r.stderr[-500:]}

        # Python projects
        pyproject = Path(worktree) / "pyproject.toml"
        if pyproject.exists() or (Path(worktree) / "setup.py").exists():
            r = subprocess.run(
                ["python3", "-m", "pytest", "--tb=short", "-q"],
                cwd=worktree, capture_output=True, text=True, timeout=120,
            )
            results["test"] = {"passed": r.returncode == 0, "output": r.stdout[-500:] + r.stderr[-500:]}

        status = "passed" if all(
            v is None or v.get("passed", True) for v in results.values()
        ) else "failed"

        return {"status": status, "results": results}

    def commit_changes(self, session_id: str, message: str) -> Optional[str]:
        """Git add + commit on the session branch. Returns commit SHA or None."""
        session_dir = SESSIONS_DIR / session_id
        meta = json.loads((session_dir / "session.json").read_text())
        worktree = meta.get("worktree_path", "")
        if not worktree or not Path(worktree).exists():
            return None

        subprocess.run(["git", "add", "-A"], cwd=worktree, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=worktree, capture_output=True, text=True,
            env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "Agent", "GIT_AUTHOR_EMAIL": "agent@workstation.local",
                 "GIT_COMMITTER_NAME": "Agent", "GIT_COMMITTER_EMAIL": "agent@workstation.local"},
        )
        if result.returncode == 0:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree, capture_output=True, text=True,
            ).stdout.strip()
            return sha
        return None

    def _record_timeline_event(self, session_id: str, event_type: str, data: dict):
        """Record raw timeline event and derived chat-facing status update."""
        events_dir = SESSIONS_DIR / session_id / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        events_file = events_dir / "events.jsonl"
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        with open(events_file, "a") as f:
            f.write(json.dumps(event) + "\n")

        try:
            from status_feed.narrator import emit_status_for_event

            emit_status_for_event(session_id, event)
        except Exception:
            # Status narration must never break executor progress.
            pass
