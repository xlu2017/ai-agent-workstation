"""
Aider Executor — direct code editing with auto-commit.

Uses Aider CLI to edit files and auto-commit changes.
Best for focused code edits where you want immediate git commits.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.base import ExecutorAdapter, TaskPacket, TaskResult, SESSIONS_DIR, TASKS_DIR


# Required: tasks fail cleanly when LITELLM_MASTER_KEY is unset.
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")


class AiderExecutor(ExecutorAdapter):
    """Execute tasks via Aider with auto-commit."""

    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        start_time = time.time()
        if not LITELLM_KEY:
            return TaskResult(
                status="failed",
                error="LITELLM_MASTER_KEY environment variable is not set",
            )
        session_dir = SESSIONS_DIR / session_id
        events_dir = session_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)

        worktree = packet.worktree_path
        if not worktree or not Path(worktree).exists():
            return TaskResult(status="failed", error="No worktree path")

        # Save task packet
        packet.save()

        self._record_timeline_event(session_id, "task_start", {
            "task_id": packet.task_id,
            "instruction": packet.instruction[:200],
            "executor": "aider",
        })

        # Build aider command
        # Aider uses OpenAI-compatible API via LiteLLM
        model_name = f"openai/{packet.model}"
        message = packet.to_markdown()

        cmd = [
            "aider",
            "--model", model_name,
            "--openai-api-key", LITELLM_KEY,
            "--openai-api-base", f"{LITELLM_URL}/v1",
            "--yes-always",  # auto-approve edits
            "--no-auto-lint",
            "--no-suggest-shell-commands",
            "--message", message,
        ]

        env = {
            **os.environ,
            "OPENAI_API_KEY": LITELLM_KEY,
            "OPENAI_API_BASE": f"{LITELLM_URL}/v1",
            "GIT_AUTHOR_NAME": "Agent",
            "GIT_AUTHOR_EMAIL": "agent@workstation.local",
            "GIT_COMMITTER_NAME": "Agent",
            "GIT_COMMITTER_EMAIL": "agent@workstation.local",
        }

        events_file = events_dir / "aider-run.log"
        files_edited = []
        commands_run = ["aider"]

        try:
            result = subprocess.run(
                cmd,
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
            )

            # Save full output
            events_file.write_text(result.stdout + "\n---STDERR---\n" + result.stderr)

            # Parse output for file edits
            for line in result.stdout.split("\n"):
                if "Wrote " in line or "Applied edit to " in line:
                    # Aider outputs "Applied edit to filename"
                    parts = line.split("Applied edit to ")
                    if len(parts) > 1:
                        files_edited.append(parts[1].strip())
                    parts = line.split("Wrote ")
                    if len(parts) > 1:
                        files_edited.append(parts[1].strip())

                self._record_timeline_event(session_id, "agent_output", {"text": line[:200]})

            exit_code = result.returncode

        except subprocess.TimeoutExpired:
            self._record_timeline_event(session_id, "task_timeout", {"task_id": packet.task_id})
            return TaskResult(
                status="failed",
                error="Aider timed out after 180s",
                duration_seconds=time.time() - start_time,
            )
        except FileNotFoundError:
            self._record_timeline_event(session_id, "task_error", {"error": "aider not installed"})
            return TaskResult(
                status="failed",
                error="aider CLI not found. Install with: pip install aider-chat",
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            self._record_timeline_event(session_id, "task_error", {"error": str(e)})
            return TaskResult(
                status="failed",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        duration = time.time() - start_time

        # Check if aider made commits (it auto-commits)
        commit_sha = None
        try:
            sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree, capture_output=True, text=True,
            )
            commit_sha = sha_result.stdout.strip()
            # Verify it's a new commit (not the same as before task started)
            log_result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                cwd=worktree, capture_output=True, text=True,
            )
            if "Agent" not in log_result.stdout and "aider" not in log_result.stdout.lower():
                commit_sha = None  # No new commit from aider
        except Exception:
            pass

        # Run validation
        validation = self.run_validation(session_id)
        tests_passed = 0
        tests_failed = 0
        if validation.get("results", {}).get("test"):
            tests_passed = 1 if validation["results"]["test"]["passed"] else 0
            tests_failed = 0 if validation["results"]["test"]["passed"] else 1

        # If aider didn't auto-commit but made changes, commit manually
        if not commit_sha and files_edited and validation["status"] == "passed":
            commit_msg = f"fix: {packet.instruction[:72]}"
            commit_sha = self.commit_changes(session_id, commit_msg)

        status = "committed" if commit_sha else ("failed" if exit_code != 0 else "needs_review")

        self._record_timeline_event(session_id, "task_complete", {
            "task_id": packet.task_id,
            "status": status,
            "files_edited": len(files_edited),
            "commit": commit_sha,
            "duration": duration,
        })

        return TaskResult(
            status=status,
            files_edited=files_edited,
            commands_run=commands_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            commit_sha=commit_sha,
            duration_seconds=duration,
        )

    def stream_events(self, session_id: str) -> Iterator[dict]:
        events_file = SESSIONS_DIR / session_id / "events" / "aider-run.log"
        if not events_file.exists():
            return
        for line in events_file.read_text().split("\n"):
            if line.strip():
                yield {"type": "aider_output", "text": line}
