"""
DeterministicExecutor — fast deterministic executor for simple local operations.

Handles cheap, direct actions without an LLM loop:
  grep, search_code, glob, find_files, read_file, read_file_range, view_file,
  list_files, git_status, git_diff, inspect_diff, apply_patch with unified diff
  text, write_file, run_tests, run_lint, run_typecheck, summarize_diff, commit.

Does not make autonomous decisions.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from adapters.execution.base import ExecutionAdapter
from execution.redaction import redact_output
from execution.results import ExecutionEvent, ExecutionResult

COMMAND_TIMEOUT = int(os.environ.get("AGENTIC_EXECUTOR_COMMAND_TIMEOUT", "60"))
PROTECTED_BRANCHES = {"main", "master", "develop", "production"}
MAX_SEARCH_RESULTS = int(os.environ.get("DETERMINISTIC_EXECUTOR_MAX_SEARCH_RESULTS", "100"))
MAX_LIST_RESULTS = int(os.environ.get("DETERMINISTIC_EXECUTOR_MAX_LIST_RESULTS", "200"))
DEFAULT_VIEW_LINES = int(os.environ.get("DETERMINISTIC_EXECUTOR_DEFAULT_VIEW_LINES", "160"))
MAX_VIEW_CHARS = int(os.environ.get("DETERMINISTIC_EXECUTOR_MAX_VIEW_CHARS", "8000"))
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", ".turbo", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


class DeterministicExecutor(ExecutionAdapter):
    """Fast deterministic executor for simple local actions."""

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
            "glob": self._exec_glob,
            "find_files": self._exec_glob,
            "search_files": self._exec_glob,
            "read_file": self._exec_read_file,
            "read_file_range": self._exec_read_file,
            "view_file": self._exec_read_file,
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
        wt_resolved = worktree.resolve()
        candidate = Path(target)
        resolved = candidate.resolve() if candidate.is_absolute() else (worktree / candidate).resolve()
        try:
            resolved.relative_to(wt_resolved)
        except ValueError as exc:
            raise PermissionError(f"Path escapes worktree: {target}") from exc
        return resolved

    def _make_event(self, event_type: str, title: str, summary: str, status: str = "completed", metadata: dict[str, Any] | None = None) -> ExecutionEvent:
        return ExecutionEvent(
            event_type=event_type,
            title=title,
            summary=redact_output(summary),
            status=status,
            metadata=metadata or {},
            source="deterministic",
        )

    def _display_path(self, worktree: Path, target: Path) -> str:
        try:
            return str(target.resolve().relative_to(worktree.resolve()))
        except (OSError, ValueError):
            return str(target)

    def _max_results(self, params: dict[str, Any], default: int = MAX_SEARCH_RESULTS) -> int:
        raw = params.get("max_results", params.get("limit", default))
        try:
            return max(1, min(int(raw), 500))
        except (TypeError, ValueError):
            return default

    def _include_pattern(self, params: dict[str, Any]) -> str:
        value = params.get("include", params.get("glob", params.get("file_glob", "")))
        return str(value).strip() if value else ""

    def _rg_available(self) -> bool:
        return shutil.which("rg") is not None

    def _sort_files_by_modified(self, worktree: Path, files: list[str]) -> list[str]:
        def key(path_text: str) -> tuple[float, str]:
            try:
                return ((worktree / path_text).stat().st_mtime, path_text)
            except OSError:
                return (0.0, path_text)

        return sorted(dict.fromkeys(files), key=key, reverse=True)

    def _should_skip_path(self, path: Path) -> bool:
        return any(part in SKIP_DIRS for part in path.parts)

    async def _exec_grep(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        """Search file contents and return candidate file paths first.

        This mirrors the OpenHands grep retrieval policy: use ripgrep when
        available, return matching files rather than flooding the LLM with all
        line matches, and only include line snippets when explicitly requested.
        """

        pattern = str(params.get("pattern", params.get("query", ""))).strip()
        if not pattern:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="grep/search_code requires a pattern or query parameter",
            )
        search_path = str(params.get("path", params.get("directory", ".")) or ".")
        target = self._validate_path(worktree, search_path) if search_path != "." else worktree
        include = self._include_pattern(params)
        max_results = self._max_results(params)
        return_lines = bool(params.get("return_lines", params.get("include_lines", False)))

        if self._rg_available():
            files = self._grep_with_ripgrep(worktree, target, pattern, include)
            line_matches = self._line_matches_with_ripgrep(worktree, target, pattern, include, max_results) if return_lines else []
        else:
            files, line_matches = self._grep_with_python(worktree, target, pattern, include, max_results if return_lines else 0)

        files = self._sort_files_by_modified(worktree, files)
        truncated = len(files) > max_results
        selected = files[:max_results]
        output: dict[str, Any] = {
            "files": selected,
            "matches": selected,
            "count": len(files),
            "truncated": truncated,
            "pattern": pattern,
            "search_path": self._display_path(worktree, target),
            "include_pattern": include,
            "mode": "candidate_files",
            "next_step": "Use read_file_range/view_file on the most relevant files before editing.",
        }
        if line_matches:
            output["line_matches"] = line_matches[:max_results]
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output=output,
            files_touched=selected,
            summary=f"Found {len(files)} candidate files for '{pattern[:40]}'",
            events=[self._make_event("command_executed", "search_code", f"candidate files: {len(files)}", metadata={"count": len(files), "truncated": truncated})],
        )

    def _grep_with_ripgrep(self, worktree: Path, target: Path, pattern: str, include: str) -> list[str]:
        cmd = ["rg", "-l", "-i", "--sortr", "modified", pattern, str(target)]
        if include:
            cmd.extend(["-g", include])
        result = subprocess.run(cmd, cwd=str(worktree), capture_output=True, text=True, timeout=30)
        if result.returncode not in (0, 1):
            raise RuntimeError(redact_output(result.stderr.strip()) or "ripgrep failed")
        return [self._display_path(worktree, Path(line.strip())) for line in result.stdout.splitlines() if line.strip()]

    def _line_matches_with_ripgrep(self, worktree: Path, target: Path, pattern: str, include: str, max_results: int) -> list[str]:
        cmd = ["rg", "-n", "-i", "--sortr", "modified", "--max-count", "20", pattern, str(target)]
        if include:
            cmd.extend(["-g", include])
        result = subprocess.run(cmd, cwd=str(worktree), capture_output=True, text=True, timeout=30)
        if result.returncode not in (0, 1):
            raise RuntimeError(redact_output(result.stderr.strip()) or "ripgrep line search failed")
        return [redact_output(line) for line in result.stdout.splitlines()[:max_results] if line.strip()]

    def _grep_with_python(self, worktree: Path, target: Path, pattern: str, include: str, line_limit: int) -> tuple[list[str], list[str]]:
        lowered = pattern.lower()
        files: list[str] = []
        line_matches: list[str] = []
        roots = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()]
        for path in roots:
            rel = self._display_path(worktree, path)
            if self._should_skip_path(path.relative_to(worktree) if path.is_relative_to(worktree) else path):
                continue
            if include and not fnmatch.fnmatch(rel, include):
                continue
            try:
                for line_number, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
                    if lowered in line.lower():
                        files.append(rel)
                        if line_limit and len(line_matches) < line_limit:
                            line_matches.append(redact_output(f"{rel}:{line_number}:{line[:240]}"))
                        break
            except OSError:
                continue
        return files, line_matches

    async def _exec_glob(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        """Find candidate files by path pattern.

        This mirrors OpenHands glob: prefer ``rg --files -g`` when available,
        fall back to Python glob, return file paths only, and cap results.
        """

        pattern = str(params.get("pattern", params.get("query", params.get("glob", "")))).strip()
        if not pattern:
            return ExecutionResult(status="failed", backend="deterministic", error="glob/find_files requires a pattern parameter")
        search_path = str(params.get("path", params.get("directory", ".")) or ".")
        target = self._validate_path(worktree, search_path) if search_path != "." else worktree
        max_results = self._max_results(params)
        if self._rg_available() and target.is_dir():
            files = self._glob_with_ripgrep(worktree, target, pattern)
        else:
            files = self._glob_with_python(worktree, target, pattern)
        files = self._sort_files_by_modified(worktree, files)
        truncated = len(files) > max_results
        selected = files[:max_results]
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"files": selected, "entries": selected, "count": len(files), "truncated": truncated, "pattern": pattern, "search_path": self._display_path(worktree, target), "mode": "candidate_files"},
            files_touched=selected,
            summary=f"Found {len(files)} files for pattern '{pattern[:60]}'",
            events=[self._make_event("command_executed", "glob", f"candidate files: {len(files)}", metadata={"count": len(files), "truncated": truncated})],
        )

    def _glob_with_ripgrep(self, worktree: Path, target: Path, pattern: str) -> list[str]:
        cmd = ["rg", "--files", str(target), "-g", pattern, "--sortr", "modified"]
        result = subprocess.run(cmd, cwd=str(worktree), capture_output=True, text=True, timeout=20)
        if result.returncode not in (0, 1):
            raise RuntimeError(redact_output(result.stderr.strip()) or "ripgrep file listing failed")
        return [self._display_path(worktree, Path(line.strip())) for line in result.stdout.splitlines() if line.strip()]

    def _glob_with_python(self, worktree: Path, target: Path, pattern: str) -> list[str]:
        files: list[str] = []
        root = target if target.is_dir() else target.parent
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = self._display_path(worktree, path)
            if self._should_skip_path(Path(rel)):
                continue
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
                files.append(rel)
        return files

    async def _exec_read_file(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        path_str = params.get("path", params.get("file", ""))
        if not path_str:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="read_file/view_file requires a path parameter",
            )
        target = self._validate_path(worktree, str(path_str))
        if not target.exists():
            return ExecutionResult(
                status="failed", backend="deterministic",
                error=f"File not found: {path_str}",
            )
        if not target.is_file():
            return await self._exec_list_files(worktree, {"path": str(path_str), "max_depth": 1}, context)

        text = target.read_text(errors="replace")
        lines = text.splitlines()
        start_line, end_line = self._view_range(params, len(lines))
        selected_lines = lines[start_line - 1:end_line]
        content = "\n".join(selected_lines)
        truncated = False
        if len(content) > MAX_VIEW_CHARS:
            content = content[:MAX_VIEW_CHARS]
            truncated = True
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={
                "content": content,
                "path": str(path_str),
                "start_line": start_line,
                "end_line": end_line,
                "total_lines": len(lines),
                "truncated": truncated,
                "next_step": "Use narrower view_range if more context is needed; avoid feeding whole files unnecessarily.",
            },
            files_touched=[str(path_str)],
            events=[self._make_event("file_read", f"Read {path_str}", f"Read lines {start_line}-{end_line} of {len(lines)}")],
        )

    def _view_range(self, params: dict[str, Any], total_lines: int) -> tuple[int, int]:
        view_range = params.get("view_range") or params.get("range")
        if isinstance(view_range, list) and view_range:
            try:
                start = int(view_range[0])
                end = int(view_range[1]) if len(view_range) > 1 else start + DEFAULT_VIEW_LINES - 1
            except (TypeError, ValueError):
                start, end = 1, min(total_lines, DEFAULT_VIEW_LINES)
        else:
            try:
                start = int(params.get("start_line", 1) or 1)
            except (TypeError, ValueError):
                start = 1
            raw_end = params.get("end_line")
            try:
                end = int(raw_end) if raw_end is not None else start + DEFAULT_VIEW_LINES - 1
            except (TypeError, ValueError):
                end = start + DEFAULT_VIEW_LINES - 1
        if end == -1:
            end = total_lines
        start = max(1, start)
        end = min(total_lines, max(start, end)) if total_lines else 0
        return start, end

    async def _exec_list_files(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        path_str = params.get("path", ".")
        target = self._validate_path(worktree, str(path_str)) if path_str != "." else worktree
        if not target.exists() or not target.is_dir():
            return ExecutionResult(
                status="failed", backend="deterministic",
                error=f"Directory not found: {path_str}",
            )
        max_depth = min(params.get("max_depth", params.get("depth", 1)) or 1, 4)
        max_results = self._max_results(params, MAX_LIST_RESULTS)
        if self._rg_available():
            result = subprocess.run(["rg", "--files", str(target), "--sortr", "modified"], cwd=str(worktree), capture_output=True, text=True, timeout=10)
            if result.returncode not in (0, 1):
                entries = []
            else:
                entries = [self._display_path(worktree, Path(line.strip())) for line in result.stdout.splitlines() if line.strip()]
        else:
            result = subprocess.run(
                ["find", str(target), "-maxdepth", str(max_depth),
                 "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*"],
                capture_output=True, text=True, timeout=10,
            )
            entries = [self._display_path(worktree, Path(l.strip())) for l in sorted(result.stdout.strip().split("\n")) if l.strip()]
        if max_depth and self._rg_available():
            root_parts = len(self._display_path(worktree, target).split("/")) if target != worktree else 0
            entries = [entry for entry in entries if len(Path(entry).parts) - root_parts <= max_depth]
        truncated = len(entries) > max_results
        return ExecutionResult(
            status="succeeded", backend="deterministic",
            output={"entries": entries[:max_results], "count": len(entries), "truncated": truncated},
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
        if params.get("path"):
            target = self._validate_path(worktree, str(params["path"]))
            cmd.extend(["--", str(target.relative_to(worktree.resolve()))])
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
        patch_text = params.get("patch", "")
        file_path = params.get("file", params.get("path", ""))
        content = params.get("content")

        if params.get("intent") and not patch_text and content is None:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="apply_patch with intent requires the agentic executor; deterministic executor only accepts unified diff text or explicit content",
            )

        if content is not None:
            if not file_path:
                return ExecutionResult(
                    status="failed", backend="deterministic",
                    error="apply_patch content mode requires a file/path parameter",
                )
            target = self._validate_path(worktree, str(file_path))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content))
            return ExecutionResult(
                status="succeeded", backend="deterministic",
                output={"path": file_path, "bytes_written": len(str(content)), "mode": "content"},
                files_touched=[str(file_path)],
                events=[self._make_event("file_edited", f"Wrote {file_path}", f"Wrote {len(str(content))} bytes")],
            )

        if not patch_text:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="apply_patch requires unified diff text in patch or explicit content",
            )

        with tempfile.NamedTemporaryFile("w", suffix=".patch", dir=str(worktree), delete=False) as handle:
            handle.write(str(patch_text))
            patch_path = Path(handle.name)
        try:
            check = subprocess.run(
                ["git", "apply", "--check", str(patch_path)],
                cwd=str(worktree), capture_output=True, text=True, timeout=30,
            )
            if check.returncode != 0:
                return ExecutionResult(
                    status="failed", backend="deterministic",
                    output={"stderr": redact_output(check.stderr)},
                    error=redact_output(check.stderr.strip()) or "Patch check failed",
                )
            result = subprocess.run(
                ["git", "apply", str(patch_path)],
                cwd=str(worktree), capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return ExecutionResult(
                    status="failed", backend="deterministic",
                    output={"stderr": redact_output(result.stderr)},
                    error=redact_output(result.stderr.strip()) or "Patch apply failed",
                )
            changed = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=str(worktree), capture_output=True, text=True, timeout=10,
            )
            files = [line for line in changed.stdout.splitlines() if line.strip()]
            return ExecutionResult(
                status="succeeded", backend="deterministic",
                output={"files": files, "mode": "unified_diff"},
                files_touched=files,
                events=[self._make_event("file_edited", "Applied patch", f"Changed {len(files)} files")],
            )
        finally:
            try:
                patch_path.unlink()
            except OSError:
                pass

    async def _exec_write_file(
        self, worktree: Path, params: dict[str, Any], context: dict[str, Any],
    ) -> ExecutionResult:
        path_str = params.get("path", "")
        if not path_str:
            return ExecutionResult(
                status="failed", backend="deterministic",
                error="write_file requires a path parameter",
            )
        content = params.get("content", "")
        return await self._exec_apply_patch(worktree, {"path": path_str, "content": str(content)}, context)

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

        from execution.commit_guard import check_duplicate_tree
        is_dup, dup_detail = check_duplicate_tree(worktree)
        if is_dup:
            return ExecutionResult(
                status="blocked", backend="deterministic",
                error=f"Commit rejected: {dup_detail}",
            )

        result = subprocess.run(
            ["git", "commit", "-m", str(message)],
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
