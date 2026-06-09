"""
AgenticExecutor — primary local agentic coding executor.

Uses a local LLM tool-calling loop to execute one bounded assigned action.
Can inspect files, edit files, run commands, run tests, and emit granular events.
Executes one bounded assigned action. Does not decide the next platform step
after its assigned action completes.

Extracted from the old local executor mechanics and rebuilt as a
platform-owned executor with no vendor naming or dependencies.

Configuration:
  AGENTIC_EXECUTOR_ENABLED=true
  AGENTIC_EXECUTOR_MAX_ITERATIONS=50
  AGENTIC_EXECUTOR_COMMAND_TIMEOUT=60
  LITELLM_URL=http://localhost:4000
  DEFAULT_MODEL=deepseek-chat
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from adapters.execution.base import ExecutionAdapter
from execution.redaction import redact_output, redact_value
from execution.results import ExecutionEvent, ExecutionResult

# --- Configuration ---

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-1234")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-chat")
MAX_ITERATIONS = int(os.environ.get("AGENTIC_EXECUTOR_MAX_ITERATIONS", "50"))
MAX_OUTPUT_CHARS = 4000
COMMAND_TIMEOUT = int(os.environ.get("AGENTIC_EXECUTOR_COMMAND_TIMEOUT", "60"))
PROTECTED_BRANCHES = {"main", "master", "develop", "production"}


# ============================================================
# TOOL DEFINITIONS — OpenAI function-calling schema
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a bash command in the workspace. Supports pipes, "
                "redirects, subshells, environment variables. Commands run with "
                "the workspace as cwd. Use for: running tests, installing deps, "
                "git operations, compilation, any shell task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command to execute. Can be multi-line.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 60, max 300)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read file contents with optional line range. "
                "Path is relative to workspace root. Returns numbered lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to workspace)"},
                    "start_line": {"type": "integer", "description": "Start line (1-indexed)"},
                    "end_line": {"type": "integer", "description": "End line (1-indexed, inclusive)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file (creates or overwrites). "
                "Creates parent directories automatically. "
                "Path is relative to workspace root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to workspace)"},
                    "content": {"type": "string", "description": "Complete file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a file by replacing exact string matches. "
                "Provide old_str (text to find) and new_str (replacement). "
                "The old_str must appear exactly once in the file. "
                "Path is relative to workspace root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to workspace)"},
                    "old_str": {"type": "string", "description": "Exact text to find and replace"},
                    "new_str": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search for a pattern across files using ripgrep (rg). "
                "Returns matching lines with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
                    "path": {"type": "string", "description": "Directory or file to search (default: workspace root)"},
                    "file_type": {"type": "string", "description": "File extension filter (e.g. 'ts', 'py')"},
                    "case_insensitive": {"type": "boolean", "description": "Case insensitive search (default false)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List directory contents. Shows files and subdirectories. "
                "Path is relative to workspace root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: workspace root)"},
                    "max_depth": {"type": "integer", "description": "Max recursion depth (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": (
                "Execute git commands in the workspace. Supports status, diff, "
                "add, commit, log, branch, checkout, stash, show, blame, etc. "
                "Do NOT push to remote or force-push."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git subcommand and arguments",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Run the project's test suite. Automatically detects test "
                "framework or you can specify a custom command."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Custom test command (optional)"},
                    "filter": {"type": "string", "description": "Test name filter/pattern (optional)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Signal task completion. MUST be called when done. "
                "Provide a clear summary and accurate status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Concise summary of what was accomplished"},
                    "status": {
                        "type": "string",
                        "enum": ["completed", "failed", "needs_review"],
                        "description": "completed | failed | needs_review",
                    },
                },
                "required": ["summary", "status"],
            },
        },
    },
]


# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================


class ToolExecutor:
    """Executes tools within a workspace context."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self._env = {
            **os.environ,
            "HOME": os.environ.get("HOME", "/home/agent"),
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", ""),
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
        }
        self.files_edited: list[str] = []
        self.commands_run: list[str] = []
        self.tests_passed: int = 0
        self.tests_failed: int = 0

    def execute(self, name: str, args: dict) -> str:
        """Dispatch tool call to handler. Returns observation string."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"ERROR: Unknown tool '{name}'"
        try:
            return handler(args)
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"

    def _tool_bash(self, args: dict) -> str:
        command = args.get("command", "")
        if not command.strip():
            return "ERROR: empty command"

        timeout = min(args.get("timeout", COMMAND_TIMEOUT), 300)
        self.commands_run.append(command[:200])

        dangerous = [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
            "> /dev/sd", "shutdown", "reboot", "init 0", "init 6",
            ":(){ :|:& };:", "fork bomb",
        ]
        cmd_lower = command.lower().strip()
        for d in dangerous:
            if d in cmd_lower:
                return f"BLOCKED: dangerous command pattern '{d}'"

        if "git push" in command and "--force" in command:
            return "BLOCKED: force push not allowed"
        if "git push" in command:
            branch = self._get_branch()
            if branch in PROTECTED_BRANCHES:
                return f"BLOCKED: cannot push to protected branch '{branch}'"

        try:
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._env,
            )
            stdout = result.stdout
            stderr = result.stderr
            output = ""
            if stdout:
                output += stdout
            if stderr:
                if output:
                    output += "\n--- stderr ---\n"
                output += stderr

            if not output.strip():
                output = "(no output)"

            if len(output) > MAX_OUTPUT_CHARS:
                half = MAX_OUTPUT_CHARS // 2
                output = (
                    output[:half]
                    + f"\n\n... [{len(output) - MAX_OUTPUT_CHARS} chars truncated] ...\n\n"
                    + output[-half:]
                )

            return f"{output}\n[exit code: {result.returncode}]"

        except subprocess.TimeoutExpired:
            return f"[command timed out after {timeout}s]"
        except Exception as e:
            return f"[execution error: {e}]"

    def _tool_read_file(self, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "ERROR: path required"

        fpath = self._resolve_path(path)
        if isinstance(fpath, str):
            return fpath

        if not fpath.exists():
            return f"File not found: {path}"
        if not fpath.is_file():
            return f"Not a file: {path}"
        if fpath.stat().st_size > 1_000_000:
            return f"File too large ({fpath.stat().st_size} bytes). Use bash with head/tail."

        try:
            content = fpath.read_text(errors="replace")
        except Exception as e:
            return f"Error reading: {e}"

        lines = content.split("\n")
        start = max(0, (args.get("start_line", 1) or 1) - 1)
        end = args.get("end_line") or len(lines)
        end = min(end, len(lines))

        selected = lines[start:end]
        if len(selected) > 500:
            selected = selected[:500]
            selected.append(f"... (file has {len(lines)} total lines, showing first 500 from range)")

        numbered = [f"{start + i + 1:4d} | {line}" for i, line in enumerate(selected)]
        header = f"[{path}] lines {start+1}-{min(end, start+len(selected))} of {len(lines)}"
        return header + "\n" + "\n".join(numbered)

    def _tool_write_file(self, args: dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return "ERROR: path required"

        fpath = self._resolve_path(path)
        if isinstance(fpath, str):
            return fpath

        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            self.files_edited.append(path)
            line_count = content.count("\n") + 1
            return f"Written {len(content)} bytes ({line_count} lines) to {path}"
        except Exception as e:
            return f"Error writing: {e}"

    def _tool_edit_file(self, args: dict) -> str:
        path = args.get("path", "")
        old_str = args.get("old_str", "")
        new_str = args.get("new_str", "")

        if not path:
            return "ERROR: path required"
        if not old_str:
            return "ERROR: old_str required"

        fpath = self._resolve_path(path)
        if isinstance(fpath, str):
            return fpath

        if not fpath.exists():
            return f"File not found: {path}"

        try:
            content = fpath.read_text()
        except Exception as e:
            return f"Error reading: {e}"

        count = content.count(old_str)
        if count == 0:
            lines = content.split("\n")
            search_lower = old_str.lower()[:50]
            near = [f"{i+1}: {l}" for i, l in enumerate(lines) if search_lower in l.lower()][:5]
            hint = "\nSimilar lines:\n" + "\n".join(near) if near else ""
            return f"old_str not found in {path}. File has {len(lines)} lines.{hint}"
        if count > 1:
            return f"old_str found {count} times — must be unique. Add more context."

        new_content = content.replace(old_str, new_str, 1)
        fpath.write_text(new_content)
        self.files_edited.append(path)

        old_lines = old_str.count("\n") + 1
        new_lines = new_str.count("\n") + 1
        return f"Edited {path}: replaced {old_lines} lines with {new_lines} lines"

    def _tool_search(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        if not pattern:
            return "ERROR: pattern required"

        search_path = args.get("path", ".")
        if search_path == ".":
            search_path = self.workspace
        else:
            resolved = self._resolve_path(search_path)
            if isinstance(resolved, str):
                return resolved
            search_path = str(resolved)

        cmd = ["rg", "--line-number", "--no-heading", "--color=never", "-M", "200"]
        if args.get("case_insensitive"):
            cmd.append("-i")
        if args.get("file_type"):
            cmd.extend(["-t", args["file_type"]])
        cmd.append(pattern)
        cmd.append(search_path)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=self.workspace,
            )
            output = result.stdout
            if not output.strip():
                return f"No matches for pattern: {pattern}"
            lines = output.strip().split("\n")
            if len(lines) > 30:
                lines = lines[:30]
                lines.append(f"... ({len(output.strip().split(chr(10)))} total matches)")
            cleaned = [line.replace(self.workspace + "/", "") for line in lines]
            return "\n".join(cleaned)
        except FileNotFoundError:
            cmd = ["grep", "-rn", "--color=never"]
            if args.get("case_insensitive"):
                cmd.append("-i")
            if args.get("file_type"):
                cmd.extend(["--include", f"*.{args['file_type']}"])
            cmd.extend([pattern, search_path])
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, cwd=self.workspace,
                )
                output = result.stdout
                if not output.strip():
                    return f"No matches for: {pattern}"
                lines = output.strip().split("\n")[:50]
                return "\n".join(l.replace(self.workspace + "/", "") for l in lines)
            except Exception as e:
                return f"Search error: {e}"
        except subprocess.TimeoutExpired:
            return "Search timed out (pattern too broad?)"
        except Exception as e:
            return f"Search error: {e}"

    def _tool_list_dir(self, args: dict) -> str:
        path = args.get("path", ".")
        max_depth = min(args.get("max_depth", 1) or 1, 4)

        if path == "." or not path:
            target = Path(self.workspace)
        else:
            resolved = self._resolve_path(path)
            if isinstance(resolved, str):
                return resolved
            target = resolved

        if not target.exists():
            return f"Directory not found: {path}"
        if not target.is_dir():
            return f"Not a directory: {path}"

        try:
            cmd = [
                "find", str(target), "-maxdepth", str(max_depth),
                "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*",
                "-not", "-name", ".git",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            entries = []
            for line in sorted(result.stdout.strip().split("\n")):
                if not line.strip():
                    continue
                rel = line.replace(str(target), ".", 1)
                if rel == ".":
                    continue
                p = Path(line)
                indicator = "/" if p.is_dir() else ""
                entries.append(f"  {rel}{indicator}")

            if len(entries) > 100:
                entries = entries[:100]
                entries.append("  ... (truncated, >100 entries)")

            return f"[{path or '.'}] ({len(entries)} items)\n" + "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {e}"

    def _tool_git(self, args: dict) -> str:
        command = args.get("command", "")
        if not command.strip():
            return "ERROR: git command required"

        blocked_ops = ["push --force", "push -f", "reset --hard HEAD~", "clean -fd"]
        for b in blocked_ops:
            if b in command:
                return f"BLOCKED: '{b}' not allowed"

        if command.startswith(("push", "force")):
            branch = self._get_branch()
            if branch in PROTECTED_BRANCHES:
                return f"BLOCKED: cannot modify protected branch '{branch}'"

        full_cmd = f"git {command}"
        self.commands_run.append(full_cmd[:200])

        try:
            result = subprocess.run(
                ["git"] + shlex.split(command),
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
                env=self._env,
            )
            output = (result.stdout + result.stderr).strip()
            if not output:
                output = "(no output)"
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
            return f"{output}\n[exit code: {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "[git command timed out]"
        except Exception as e:
            return f"[git error: {e}]"

    def _tool_run_tests(self, args: dict) -> str:
        command = args.get("command", "")
        test_filter = args.get("filter", "")

        if not command:
            ws = Path(self.workspace)
            if (ws / "package.json").exists():
                pkg = json.loads((ws / "package.json").read_text())
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    command = "npm test"
                    if "vitest" in scripts.get("test", ""):
                        command = "npx vitest run"
                    elif "jest" in scripts.get("test", ""):
                        command = "npx jest"
            elif (ws / "pyproject.toml").exists() or (ws / "pytest.ini").exists():
                command = "python3 -m pytest -v"
            elif (ws / "Cargo.toml").exists():
                command = "cargo test"
            elif (ws / "go.mod").exists():
                command = "go test ./..."
            elif (ws / "Makefile").exists():
                command = "make test"

            if not command:
                return "Could not detect test framework. Provide a command."

        if test_filter:
            if "vitest" in command or "jest" in command:
                command += f" -t '{test_filter}'"
            elif "pytest" in command:
                command += f" -k '{test_filter}'"
            elif "cargo" in command:
                command += f" {test_filter}"

        self.commands_run.append(f"[tests] {command}")

        try:
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=120,
                env=self._env,
            )
            output = result.stdout + result.stderr
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[-MAX_OUTPUT_CHARS:]

            pass_match = re.search(r"(\d+)\s+pass", output, re.IGNORECASE)
            fail_match = re.search(r"(\d+)\s+fail", output, re.IGNORECASE)
            if pass_match:
                self.tests_passed = int(pass_match.group(1))
            if fail_match:
                self.tests_failed = int(fail_match.group(1))

            status_str = "PASSED" if result.returncode == 0 else "FAILED"
            return f"[Tests {status_str} - exit {result.returncode}]\n{output}"
        except subprocess.TimeoutExpired:
            return "[tests timed out after 120s]"
        except Exception as e:
            return f"[test error: {e}]"

    def _resolve_path(self, path: str) -> Path | str:
        """Resolve path relative to workspace, with security check."""
        if path.startswith("/"):
            fpath = Path(path)
        else:
            fpath = Path(self.workspace) / path

        try:
            resolved = fpath.resolve()
            ws_resolved = Path(self.workspace).resolve()
            if not (str(resolved).startswith(str(ws_resolved)) or str(resolved).startswith("/tmp")):
                return f"BLOCKED: path '{path}' escapes workspace boundary"
        except Exception:
            return f"BLOCKED: cannot resolve path '{path}'"
        return fpath

    def _get_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace, capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""


# ============================================================
# LLM CLIENT
# ============================================================


def _call_llm(messages: list[dict], model: str = DEFAULT_MODEL) -> dict:
    """Call LiteLLM proxy for chat completion with tools."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 4096,
        "temperature": 0.0,
    }).encode()

    req = urllib.request.Request(
        f"{LITELLM_URL}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LITELLM_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"LLM call failed ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM unreachable at {LITELLM_URL}: {e}") from e


# ============================================================
# AGENT LOOP
# ============================================================

SYSTEM_PROMPT_TEMPLATE = """You are an autonomous coding agent executing a single bounded action in a workspace.

## Workspace
Working directory: {workspace}

## Available Tools
- **bash**: Run any shell command
- **read_file**: Read file with line numbers (supports line ranges)
- **write_file**: Create or overwrite a file
- **edit_file**: Replace exact string in a file (search & replace)
- **search**: Search codebase with regex (uses ripgrep)
- **list_dir**: List directory contents
- **git**: Run git commands (status, diff, add, commit, log, branch, etc.)
- **run_tests**: Run test suite (auto-detects framework)
- **finish**: Signal completion — MUST call when done

## Rules
1. Work ONLY within the workspace directory.
2. Be efficient — read key files, then implement.
3. Use edit_file for targeted changes (preferred over write_file for existing files).
4. Run tests after making changes to verify correctness.
5. Call finish() when the task is complete or when you determine it cannot be done.
6. If something fails, try an alternative approach before giving up.
7. Do NOT push to remote. Do NOT modify protected branches (main/master/develop).
8. Commit your changes to the current branch when task is complete.

## Current Branch
{branch}
"""


def _prune_messages(messages: list[dict], max_chars: int = 200000) -> None:
    """Prune message history to stay within context limits."""
    total = sum(len(str(m.get("content", "") or "")) for m in messages)
    if total <= max_chars:
        return
    for i in range(2, len(messages)):
        if total <= max_chars:
            break
        msg = messages[i]
        content = msg.get("content", "") or ""
        if msg.get("role") == "tool" and len(content) > 500:
            old_len = len(content)
            msg["content"] = content[:200] + "\n... [truncated to fit context] ...\n" + content[-200:]
            total -= (old_len - len(msg["content"]))
    while total > max_chars and len(messages) > 4:
        idx = 2
        if idx >= len(messages):
            break
        msg = messages[idx]
        removed_size = len(str(msg.get("content", "") or ""))
        messages.pop(idx)
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = {tc.get("id") for tc in msg["tool_calls"] if isinstance(tc, dict)}
            while idx < len(messages) and messages[idx].get("role") == "tool":
                if messages[idx].get("tool_call_id") in tool_call_ids:
                    orphan = messages.pop(idx)
                    removed_size += len(str(orphan.get("content", "") or ""))
                else:
                    break
        elif msg.get("role") == "tool" and msg.get("tool_call_id"):
            orphan_id = msg["tool_call_id"]
            for prev in messages[:idx]:
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    prev["tool_calls"] = [tc for tc in prev["tool_calls"] if tc.get("id") != orphan_id]
        total -= removed_size


def _summarize_args(tool_name: str, args: dict) -> str:
    """Create a short summary of tool args for event logging."""
    if tool_name == "bash":
        return args.get("command", "")[:80]
    elif tool_name in ("read_file", "write_file", "edit_file"):
        return args.get("path", "")
    elif tool_name == "search":
        return f"/{args.get('pattern', '')}/"
    elif tool_name == "git":
        return args.get("command", "")[:60]
    elif tool_name == "run_tests":
        return args.get("command", "(auto-detect)")[:60]
    elif tool_name == "list_dir":
        return args.get("path", ".")
    return str(args)[:60]


def _run_agent_loop(
    instruction: str,
    workspace: str,
    model: str = DEFAULT_MODEL,
    max_iterations: int = MAX_ITERATIONS,
    event_callback: Any = None,
    plan_context: str = "",
) -> tuple[str, str, list[str], int, int, list[str]]:
    """Run the LLM tool-calling agent loop.

    Returns: (status, summary, files_edited, tests_passed, tests_failed, commands_run)
    """
    executor = ToolExecutor(workspace)
    branch = executor._get_branch() or "unknown"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(workspace=workspace, branch=branch)
    if plan_context:
        system_prompt += f"\n## Advisory Plan from agent-core\n{plan_context}\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    status = "completed"
    summary = ""

    for iteration in range(max_iterations):
        if event_callback:
            event_callback(
                "action_progress",
                f"Agent iteration {iteration + 1}/{max_iterations}",
                {"iteration": iteration + 1, "tools_used": len(executor.commands_run), "files_edited": len(executor.files_edited)},
            )

        _prune_messages(messages, max_chars=200000)

        try:
            response = _call_llm(messages, model)
        except RuntimeError as e:
            error_str = str(e)
            if "ContextWindowExceeded" in error_str or "context length" in error_str:
                _prune_messages(messages, max_chars=60000)
                try:
                    response = _call_llm(messages, model)
                except RuntimeError as e2:
                    return ("failed", f"LLM error after pruning: {e2}", executor.files_edited,
                            executor.tests_passed, executor.tests_failed, executor.commands_run)
            else:
                return ("failed", f"LLM error: {e}", executor.files_edited,
                        executor.tests_passed, executor.tests_failed, executor.commands_run)

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        if not message.get("tool_calls"):
            content = message.get("content", "")
            if content:
                summary = content[:500]
            if finish_reason == "stop":
                status = "completed"
            break

        assistant_msg = {
            "role": "assistant",
            "content": message.get("content", None),
            "tool_calls": message["tool_calls"],
        }
        messages.append(assistant_msg)

        for tool_call in message.get("tool_calls", []):
            fn = tool_call.get("function", {})
            tool_name = fn.get("name", "")
            tool_call_id = tool_call.get("id", str(uuid.uuid4()))

            try:
                tool_args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            if tool_name == "finish":
                summary = tool_args.get("summary", "Task completed")
                status = tool_args.get("status", "completed")
                return (status, summary, executor.files_edited,
                        executor.tests_passed, executor.tests_failed, executor.commands_run)

            observation = executor.execute(tool_name, tool_args)

            if event_callback:
                output_preview = redact_output(observation[:2000]) if observation else "(no output)"
                event_callback(
                    "action_progress",
                    f"Tool: {tool_name}",
                    {"tool": tool_name, "args_summary": _summarize_args(tool_name, tool_args), "type": "tool_output", "output": output_preview},
                )

            messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": observation})

    else:
        summary = f"Reached max iterations ({max_iterations}) without calling finish"
        status = "needs_review"

    return (status, summary, executor.files_edited,
            executor.tests_passed, executor.tests_failed, executor.commands_run)


# ============================================================
# AGENTIC EXECUTOR ADAPTER
# ============================================================

# Actions supported by the agentic executor
AGENTIC_ACTIONS = {
    "autonomous_code_edit",
    "investigate_and_patch",
    "repair_test_failure",
    "apply_patch",       # with intent (deterministic handles exact patch)
    "run_tests",         # when repair/diagnosis needed
    "run_command",       # when interpretation needed
    "read_file",         # if routed here
    "search_code",       # if routed here
}


class AgenticExecutor(ExecutionAdapter):
    """Primary local agentic coding executor.

    Uses LLM tool-calling loop to execute one bounded assigned action.
    Does not decide the next platform step after completion.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}

    def is_available(self) -> bool:
        """Check if the model gateway (LiteLLM) is reachable."""
        import urllib.request

        try:
            urllib.request.urlopen(f"{LITELLM_URL}/health/liveliness", timeout=3)
            return True
        except Exception:
            return False

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> ExecutionResult:
        start_ms = int(time.time() * 1000)
        events: list[ExecutionEvent] = []

        if not worktree_path or not Path(worktree_path).exists():
            return ExecutionResult(
                status="failed",
                backend="agentic",
                error=f"Workspace directory not found: {worktree_path}",
                summary="Cannot execute: workspace directory not found",
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        # Protected branch check
        branch = self._get_current_branch(worktree_path)
        if branch in PROTECTED_BRANCHES:
            return ExecutionResult(
                status="blocked",
                backend="agentic",
                error=f"Cannot execute on protected branch: {branch}",
                summary=f"Blocked: execution on '{branch}' is not allowed",
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        # Build instruction from action + params
        instruction = self._build_instruction(action_name, params, context)

        # Event callback
        def event_callback(event_type: str, message: str, metadata: dict | None = None):
            evt = ExecutionEvent(
                event_type=event_type,
                title=message[:80],
                summary=redact_output(message),
                status="running",
                metadata=redact_value(metadata or {}),
                redacted=True,
                source="agentic",
            )
            events.append(evt)

        event_callback("action_progress", f"Agentic executor starting: {action_name}", {
            "workspace": worktree_path,
            "action": action_name,
        })

        plan_context = context.get("plan_context", "")

        try:
            (status, summary, files_edited,
             tests_passed, tests_failed, commands_run) = _run_agent_loop(
                instruction=instruction,
                workspace=worktree_path,
                model=context.get("model", DEFAULT_MODEL),
                max_iterations=MAX_ITERATIONS,
                event_callback=event_callback,
                plan_context=plan_context,
            )
        except Exception as e:
            event_callback("agent_error", f"Agent loop crashed: {e}")
            return ExecutionResult(
                status="failed",
                backend="agentic",
                error=redact_output(str(e)),
                summary=f"Execution crashed",
                events=events,
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        # Map old status names to canonical
        status_map = {"completed": "succeeded", "needs_review": "needs_review", "failed": "failed"}
        canonical_status = status_map.get(status, status)

        event_callback("action_progress", f"Agentic executor finished: {canonical_status}", {
            "status": canonical_status,
            "files_edited": files_edited,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
        })
        # Mark final event as completed
        if events:
            events[-1].status = "completed" if canonical_status == "succeeded" else canonical_status

        return ExecutionResult(
            status=canonical_status,
            backend="agentic",
            summary=redact_output(summary),
            output=redact_value({
                "files_edited": files_edited,
                "commands_run": len(commands_run),
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
            }),
            files_touched=files_edited,
            events=events,
            duration_ms=int(time.time() * 1000) - start_ms,
        )

    def _build_instruction(self, action_name: str, params: dict[str, Any], context: dict[str, Any]) -> str:
        """Build a natural-language instruction for the agent loop from action + params."""
        parts = [f"Execute action: {action_name}"]

        if action_name == "autonomous_code_edit":
            parts.append(f"Task: {params.get('instruction', params.get('intent', 'Make the requested changes'))}")
        elif action_name == "investigate_and_patch":
            parts.append(f"Investigate and fix: {params.get('issue', params.get('intent', 'Investigate the issue'))}")
        elif action_name == "repair_test_failure":
            parts.append(f"Fix failing tests: {params.get('test_output', params.get('intent', 'Repair test failures'))}")
        elif action_name == "apply_patch":
            if params.get("intent"):
                parts.append(f"Apply changes: {params['intent']}")
                if params.get("path"):
                    parts.append(f"Target file: {params['path']}")
            elif params.get("patch"):
                parts.append(f"Apply this patch:\n{params['patch']}")
        elif action_name == "run_tests":
            cmd = params.get("command", "")
            parts.append(f"Run tests{f': {cmd}' if cmd else ' (auto-detect)'}")
            if params.get("purpose"):
                parts.append(f"Purpose: {params['purpose']}")
        elif action_name == "run_command":
            parts.append(f"Run: {params.get('command', '')}")
        else:
            parts.append(f"Parameters: {json.dumps(params, indent=2)}")

        if context.get("rationale"):
            parts.append(f"Rationale: {context['rationale']}")

        return "\n\n".join(parts)

    def _get_current_branch(self, worktree: str) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""

    def run_task(self, session_id: str, packet: Any) -> Any:
        """Bridge from the legacy TaskPacket/TaskResult interface.

        Translates a TaskPacket (from executors/base.py) into an
        execute_action() call and returns a TaskResult so callers like
        prompt_handler, executor_runner, and queue can use AgenticExecutor
        without changing their call sites.
        """
        import asyncio

        action_name = "autonomous_code_edit"
        params = {"intent": packet.instruction}
        context = {
            "branch": getattr(packet, "branch", "main"),
            "model": getattr(packet, "model", os.environ.get("DEFAULT_MODEL", "deepseek-chat")),
            "execution_mode": getattr(packet, "execution_mode", "finite"),
        }

        # Run the async execute_action in a new event loop (since run_task
        # is called synchronously from run_in_executor threads).
        try:
            loop = asyncio.new_event_loop()
            exec_result = loop.run_until_complete(
                self.execute_action(
                    session_id=session_id,
                    worktree_path=getattr(packet, "worktree_path", ""),
                    action_name=action_name,
                    params=params,
                    context=context,
                )
            )
        finally:
            loop.close()

        # Convert ExecutionResult → TaskResult
        from executors.base import TaskResult

        return TaskResult(
            status=exec_result.status,
            summary=exec_result.summary or "",
            error=exec_result.error or None,
            files_edited=exec_result.files_touched or [],
            commands_run=[],
            tests_passed=0,
            tests_failed=0,
            duration_seconds=exec_result.duration_ms / 1000.0 if exec_result.duration_ms else 0.0,
        )
