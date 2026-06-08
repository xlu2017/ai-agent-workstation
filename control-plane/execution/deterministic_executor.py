"""
DeterministicExecutor — fast deterministic executor for simple local operations.

Handles cheap, direct actions without an LLM loop:
  grep, search_code, read_file, list_files, git_status, git_diff,
  inspect_diff, apply_patch (exact content), write_file, run_tests,
  run_lint, run_typecheck, summarize_diff, commit.

Does not make autonomous decisions.

Configuration:
  ALLOW_DETERMINISTIC_EXECUTOR=true
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from adapters.execution.base import ExecutionAdapter
from execution.redaction import redact_output, redact_value
from execution.results import ExecutionEvent, ExecutionResult

COMMAND_TIMEOUT = int(os.environ.get("AGENTIC_EXECUTOR_COMMAND_TIMEOUT", "60"))
PROTECTED_BRANCHES = {"main", "master", "develop", "production"}


class DeterministicExecutor(ExecutionAdapter):
    """Fast deterministic executor for simple local actions.

    Executes actions directly on the filesystem. All path operations
    are sandboxed to the worktree directory. No LLM, no autonomous decisions.
    """

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> ExecutionResult:
        start_ms = int(time.time() * 1000)
        wt = Path(worktree_path) if worktree_path else Path(".")

        dispatch = {
            "grep": self._exec_grep,
            "search_code": self._exec_grep,
            "read_file": self._exec_read_file,
            "list_files": self._exec_list_files,
            "git_status": self._exec_git_status,
            "git_diff": self._exec_git_diff,
            "inspect_diff": self._exec_git_diff,
            "summarize_diff": self._exec_summarize_diff,
            "apply_patch": self._exec_apply_patch,
            "write_file": self._exec_write_file,
            "run_tests": self._exec_run_tests,
            "run_lint": self._exec_run_lint,
            "run_typecheck": self._exec_run_typecheck,
            "commit": self._exec_commit,
        }

        handler = dispatch.get(action_name)
        if handler is None:
            return ExecutionResult(
                status="failed",
                backend="deterministic",
                error=f"Deterministic executor does not support action: {action_name}",
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        try:
            result = await handler(wt, params, context)
            result.duration_ms = int(time.time() * 1000) - start_ms
            return result
        except Exception as e:
            return ExecutionResult(
                status="failed",
                backend="deterministic",
                error=redact_output(str(e)),
                duration_ms=int(time.time() * 1000) - start_ms,
            )

    def _validate_path(self, worktree: Path, target: str) -> Path:
        """Ensure the target path does not escape the worktree."""
        resolved = (worktree / target).resolve()
        wt_resolved = worktree.resolve()
        if not str(resolved).startswith(str(wt_resolved)):
            raise PermissionError(f"Path escapes worktree: {target}")
        return resolved

    def _make_event(self, event_type: str, title: str, summary: str, status: str = "completed") -> ExecutionEvent:
        return ExecutionEvent(
            event_type=event_type,
            title=title,
            summary=redact_output(summary),
            status=status,
            source="deterministic",
        )

    async def _exec_grep(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        pattern = params.get("pattern", params.get("query", ""))
        if not pattern:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="grep/search_code requires a pattern parameter",
            )
        result = subprocess.run(
            ["grep", "-rn", pattern, "."],
            cwd=str(worktree), capture_output=True, text=True, timeout=30,
        )
        matches = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"matches": matches[:100], "count": len(matches)},
            summary=f"Found {len(matches)} matches for '{pattern[:40]}'",
            events=[self._make_event("command_executed", "grep", f"grep -rn {pattern[:40]}")],
        )

    async def _exec_read_file(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        path_str = params.get("path", "")
        if not path_str:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="read_file requires a path parameter",
            )
        target = self._validate_path(worktree, path_str)
        if not target.exists():
            return ExecutionResult(
                status="failed", backend="deterministic",
                error=f"File not found: {path_str}",
            )
        content = target.read_text(errors="replace")
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"content": content, "path": path_str},
            files_touched=[path_str],
            events=[self._make_event("file_read", f"Read {path_str}", f"Read {len(content)} bytes")],
        )

    async def _exec_list_files(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        path_str = params.get("path", ".")
        target = self._validate_path(worktree, path_str) if path_str != "." else worktree
        if not target.exists() or not target.is_dir():
            return ExecutionResult(
                status="failed", backend="deterministic",
                error=f"Directory not found: {path_str}",
            )
        max_depth = min(params.get("max_depth", 1) or 1, 4)
        result = subprocess.run(
            ["find", str(target), "-maxdepth", str(max_depth),
             "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*"],
            capture_output=True, text=True, timeout=10,
        )
        entries = [l.replace(str(worktree) + "/", "") for l in sorted(result.stdout.strip().split("\n")) if l.strip()]
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"entries": entries[:200], "count": len(entries)},
            summary=f"Listed {len(entries)} entries in {path_str}",
        )

    async def _exec_git_status(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(worktree), capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"status_lines": lines, "clean": len(lines) == 0},
            summary=f"{'Clean' if not lines else f'{len(lines)} changes'}",
            events=[self._make_event("command_executed", "git status", f"{len(lines)} changes")],
        )

    async def _exec_git_diff(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        cmd = ["git", "diff"]
        if params.get("staged"):
            cmd.append("--staged")
        if params.get("stat_only"):
            cmd.append("--stat")
        result = subprocess.run(
            cmd, cwd=str(worktree), capture_output=True, text=True, timeout=30,
        )
        diff_text = result.stdout[:8000] if result.stdout else ""
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"diff": diff_text},
            summary=f"Diff: {len(diff_text)} chars",
        )

    async def _exec_summarize_diff(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        stat_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(worktree), capture_output=True, text=True, timeout=30,
        )
        diff_stat = stat_result.stdout.strip() if stat_result.stdout else "(no changes)"
        full_result = subprocess.run(
            ["git", "diff"],
            cwd=str(worktree), capture_output=True, text=True, timeout=30,
        )
        diff_text = full_result.stdout[:8000] if full_result.stdout else ""
        files = []
        for line in (stat_result.stdout or "").strip().split("\n"):
            if "|" in line:
                files.append(line.split("|")[0].strip())
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"diff_stat": diff_stat, "diff": diff_text, "files": files},
            files_touched=files,
            summary=f"Diff summary: {len(files)} files changed",
        )

    async def _exec_apply_patch(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        file_path = params.get("file", params.get("path", ""))
        content = params.get("content", params.get("patch", ""))
        if not file_path:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="apply_patch requires a file/path parameter",
            )
        target = self._validate_path(worktree, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"path": file_path, "bytes_written": len(content)},
            files_touched=[file_path],
            events=[self._make_event("file_edited", f"Wrote {file_path}", f"Wrote {len(content)} bytes")],
        )

    async def _exec_write_file(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        return await self._exec_apply_patch(worktree, params, context)

    async def _exec_run_tests(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        command = params.get("command", "")
        target = params.get("target", "")
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
            command, shell=True, cwd=str(worktree),
            capture_output=True, text=True, timeout=300,
        )
        status = "succeeded" if result.returncode == 0 else "failed"
        return ExecutionResult(
            status=status, backend="deterministic",
            output={
                "stdout": redact_output(result.stdout[-4000:] if result.stdout else ""),
                "stderr": redact_output(result.stderr[-2000:] if result.stderr else ""),
                "returncode": result.returncode,
            },
            error=redact_output(result.stderr[-500:]) if result.returncode != 0 else "",
            events=[self._make_event("test_completed", "Tests", f"exit {result.returncode}", status)],
        )

    async def _exec_run_lint(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        command = params.get("command", "")
        if not command:
            if (worktree / "package.json").exists():
                command = "npm run lint"
            elif (worktree / "pyproject.toml").exists():
                command = "python -m ruff check ."
            else:
                return ExecutionResult(
                    status="skipped", backend="deterministic",
                    summary="No lint command detected",
                )
        result = subprocess.run(
            command, shell=True, cwd=str(worktree),
            capture_output=True, text=True, timeout=120,
        )
        status = "succeeded" if result.returncode == 0 else "failed"
        return ExecutionResult(
            status=status, backend="deterministic",
            output={"stdout": redact_output(result.stdout[-4000:]), "returncode": result.returncode},
            error=redact_output(result.stderr[-500:]) if result.returncode != 0 else "",
        )

    async def _exec_run_typecheck(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        command = params.get("command", "")
        if not command:
            if (worktree / "tsconfig.json").exists():
                command = "npx tsc --noEmit"
            elif (worktree / "pyproject.toml").exists():
                command = "python -m mypy ."
            else:
                return ExecutionResult(
                    status="skipped", backend="deterministic",
                    summary="No typecheck command detected",
                )
        result = subprocess.run(
            command, shell=True, cwd=str(worktree),
            capture_output=True, text=True, timeout=120,
        )
        status = "succeeded" if result.returncode == 0 else "failed"
        return ExecutionResult(
            status=status, backend="deterministic",
            output={"stdout": redact_output(result.stdout[-4000:]), "returncode": result.returncode},
            error=redact_output(result.stderr[-500:]) if result.returncode != 0 else "",
        )

    async def _exec_commit(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        message = params.get("message", "")
        if not message:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="commit requires a non-empty message parameter",
            )
        # Protected branch check
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(worktree), capture_output=True, text=True, timeout=5,
        )
        branch = branch_result.stdout.strip()
        if branch in PROTECTED_BRANCHES:
            return ExecutionResult(
                status="blocked", backend="deterministic",
                error=f"Cannot commit on protected branch: {branch}",
            )

        subprocess.run(["git", "add", "-A"], cwd=str(worktree), capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(worktree), capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree), capture_output=True, text=True,
            )
            commit_hash = hash_result.stdout.strip()
            return ExecutionResult(
                status="succeeded", backend="deterministic",
                output={"commit_hash": commit_hash, "message": message},
                events=[self._make_event("command_executed", "git commit", f"Committed: {commit_hash[:8]}")],
            )
        return ExecutionResult(
            status="failed", backend="deterministic",
            output={"stdout": result.stdout, "stderr": redact_output(result.stderr)},
            error=redact_output(result.stderr.strip()) or "Commit failed",
        )
