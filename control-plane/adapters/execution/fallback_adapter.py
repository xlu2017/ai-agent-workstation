"""
FallbackExecutorAdapter — dev/test/simple local fallback executor.

Supports: grep, read_file, run_tests, summarize_diff, commit, apply_patch.
Runtime safety: refuses to read/write outside the worktree.

Use only when:
  EXECUTOR_BACKEND=fallback
or:
  ALLOW_FALLBACK_EXECUTOR=true
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from adapters.execution.base import ExecutionAdapter


class FallbackExecutorAdapter(ExecutionAdapter):
    """Local fallback executor for dev/test environments.

    Executes actions directly on the filesystem. All path operations
    are sandboxed to the worktree directory.
    """

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        start_ms = int(time.time() * 1000)
        wt = Path(worktree_path)

        dispatch = {
            "grep": self._exec_grep,
            "read_file": self._exec_read_file,
            "run_tests": self._exec_run_tests,
            "summarize_diff": self._exec_summarize_diff,
            "commit": self._exec_commit,
            "apply_patch": self._exec_apply_patch,
        }

        handler = dispatch.get(action_name)
        if handler is None:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": f"Fallback executor does not support action: {action_name}",
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

        try:
            result = await handler(wt, params, context)
            result["duration_ms"] = int(time.time() * 1000) - start_ms
            return result
        except Exception as e:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": str(e),
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

    def _validate_path(self, worktree: Path, target: str) -> Path:
        """Ensure the target path does not escape the worktree."""
        resolved = (worktree / target).resolve()
        wt_resolved = worktree.resolve()
        if not str(resolved).startswith(str(wt_resolved)):
            raise PermissionError(f"Path escapes worktree: {target}")
        return resolved

    async def _exec_grep(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        pattern = params.get("pattern", "")
        if not pattern:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": "grep requires a pattern parameter",
                "files_touched": [],
            }
        result = subprocess.run(
            ["grep", "-rn", pattern, "."],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=30,
        )
        matches = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {
            "status": "succeeded",
            "backend": "fallback",
            "output": {"matches": matches, "count": len(matches)},
            "error": "",
            "files_touched": [],
        }

    async def _exec_read_file(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        path_str = params.get("path", "")
        if not path_str:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": "read_file requires a path parameter",
                "files_touched": [],
            }
        target = self._validate_path(worktree, path_str)
        if not target.exists():
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": f"File not found: {path_str}",
                "files_touched": [],
            }
        content = target.read_text(errors="replace")
        return {
            "status": "succeeded",
            "backend": "fallback",
            "output": {"content": content, "path": path_str},
            "error": "",
            "files_touched": [path_str],
        }

    async def _exec_run_tests(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        command = params.get("command", "")
        target = params.get("target", "")
        # Default test commands
        if not command:
            if (worktree / "package.json").exists():
                command = "npm test"
            elif (worktree / "pyproject.toml").exists():
                command = "python -m pytest"
            elif (worktree / "Makefile").exists():
                command = "make test"
            else:
                command = "echo 'No test runner found'"
        if target:
            command = f"{command} {target}"
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=300,
        )
        status = "succeeded" if result.returncode == 0 else "failed"
        return {
            "status": status,
            "backend": "fallback",
            "output": {
                "stdout": result.stdout[-4000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
                "returncode": result.returncode,
            },
            "error": result.stderr[-500:] if result.returncode != 0 else "",
            "files_touched": [],
        }

    async def _exec_summarize_diff(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff_stat = result.stdout.strip() if result.stdout else "(no changes)"
        result_full = subprocess.run(
            ["git", "diff"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff_text = result_full.stdout[:8000] if result_full.stdout else ""
        files = []
        for line in (result.stdout or "").strip().split("\n"):
            if "|" in line:
                files.append(line.split("|")[0].strip())
        return {
            "status": "succeeded",
            "backend": "fallback",
            "output": {"diff_stat": diff_stat, "diff": diff_text, "files": files},
            "error": "",
            "files_touched": files,
        }

    async def _exec_commit(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        message = params.get("message", "")
        if not message:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": "commit requires a non-empty message parameter",
                "files_touched": [],
            }
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=str(worktree), capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree),
                capture_output=True,
                text=True,
            )
            commit_hash = hash_result.stdout.strip()
            return {
                "status": "succeeded",
                "backend": "fallback",
                "output": {"commit_hash": commit_hash, "message": message},
                "error": "",
                "files_touched": [],
            }
        return {
            "status": "failed",
            "backend": "fallback",
            "output": {"stdout": result.stdout, "stderr": result.stderr},
            "error": result.stderr.strip() or "Commit failed",
            "files_touched": [],
        }

    async def _exec_apply_patch(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        file_path = params.get("file", params.get("path", ""))
        content = params.get("content", "")
        if not file_path:
            return {
                "status": "failed",
                "backend": "fallback",
                "output": {},
                "error": "apply_patch requires a file/path parameter",
                "files_touched": [],
            }
        target = self._validate_path(worktree, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {
            "status": "succeeded",
            "backend": "fallback",
            "output": {"path": file_path, "bytes_written": len(content)},
            "error": "",
            "files_touched": [file_path],
        }
