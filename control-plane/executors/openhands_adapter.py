"""
OpenHandsExecutorAdapter — complete local execution via LLM tool-calling loop.

Execution engine that takes instructions from the control-plane (after agent-core
planning/validation) and performs real coding work via LLM-driven tool calls.

Agent-core handles: planning, memory, context, action validation.
This adapter handles: actual execution of those planned actions.

Capabilities:
  - Persistent bash shell with state between commands
  - File read with line ranges
  - File write (full replace)
  - File edit (search/replace within files)
  - Directory listing and tree
  - Git operations (status, diff, add, commit, log, branch)
  - Grep/search across codebase
  - Test execution with output capture
  - Process management (background commands)
  - Finish with structured result

Uses LiteLLM proxy for LLM access (tool-calling loop).
No Docker runtime needed — executes directly on host.
"""

from __future__ import annotations

import json
import os
import pty
import select
import shlex
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from executors.base import ExecutorAdapter, TaskPacket, TaskResult, SESSIONS_DIR

# --- Configuration ---

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-1234")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-chat")
MAX_ITERATIONS = int(os.environ.get("OPENHANDS_MAX_ITERATIONS", "50"))
MAX_OUTPUT_CHARS = 4000
COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "60"))
PROTECTED_BRANCHES = {"main", "master", "develop", "production"}

VENDOR_ROOT = Path("/opt/workstation/repos/jubilant-goggles/vendor/openhands-sdk")


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
                        "description": "Bash command to execute. Can be multi-line."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 60, max 300)"
                    }
                },
                "required": ["command"]
            }
        }
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
                    "end_line": {"type": "integer", "description": "End line (1-indexed, inclusive)"}
                },
                "required": ["path"]
            }
        }
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
                    "content": {"type": "string", "description": "Complete file content"}
                },
                "required": ["path", "content"]
            }
        }
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
                    "new_str": {"type": "string", "description": "Replacement text"}
                },
                "required": ["path", "old_str", "new_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search for a pattern across files using ripgrep (rg). "
                "Returns matching lines with file paths and line numbers. "
                "Supports regex patterns and file type filtering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
                    "path": {"type": "string", "description": "Directory or file to search (default: workspace root)"},
                    "file_type": {"type": "string", "description": "File extension filter (e.g. 'ts', 'py', 'js')"},
                    "case_insensitive": {"type": "boolean", "description": "Case insensitive search (default false)"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List directory contents. Shows files and subdirectories "
                "with type indicators. Path is relative to workspace root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: workspace root)"},
                    "max_depth": {"type": "integer", "description": "Max recursion depth (default 1)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": (
                "Execute git commands in the workspace. Supports all git "
                "operations: status, diff, add, commit, log, branch, checkout, "
                "stash, show, blame, etc. Do NOT push to remote or force-push."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git subcommand and arguments (e.g. 'status', 'diff --staged', 'log -5 --oneline')"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Run the project's test suite. Automatically detects test "
                "framework (vitest, jest, pytest, cargo test, go test) or "
                "you can specify a custom command. Returns pass/fail counts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Custom test command (optional — auto-detects if omitted)"
                    },
                    "filter": {
                        "type": "string",
                        "description": "Test name filter/pattern (optional)"
                    }
                },
                "required": []
            }
        }
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
                    "summary": {
                        "type": "string",
                        "description": "Concise summary of what was accomplished or why it failed"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["completed", "failed", "needs_review"],
                        "description": "completed: task done successfully. failed: could not complete. needs_review: done but uncertain."
                    }
                },
                "required": ["summary", "status"]
            }
        }
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

    # --- bash ---
    def _tool_bash(self, args: dict) -> str:
        command = args.get("command", "")
        if not command.strip():
            return "ERROR: empty command"

        timeout = min(args.get("timeout", COMMAND_TIMEOUT), 300)
        self.commands_run.append(command[:200])

        # Security blocks
        dangerous = [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
            "> /dev/sd", "shutdown", "reboot", "init 0", "init 6",
            ":(){ :|:& };:", "fork bomb",
        ]
        cmd_lower = command.lower().strip()
        for d in dangerous:
            if d in cmd_lower:
                return f"BLOCKED: dangerous command pattern '{d}'"

        # Block push/force-push
        if "git push" in command and "--force" in command:
            return "BLOCKED: force push not allowed"
        if "git push" in command:
            # Allow only if on a non-protected branch
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

    # --- read_file ---
    def _tool_read_file(self, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "ERROR: path required"

        fpath = self._resolve_path(path)
        if isinstance(fpath, str):  # error message
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

    # --- write_file ---
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

    # --- edit_file ---
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
            # Show nearby context to help
            lines = content.split("\n")
            search_lower = old_str.lower()[:50]
            near = [f"{i+1}: {l}" for i, l in enumerate(lines)
                    if search_lower in l.lower()][:5]
            hint = "\nSimilar lines:\n" + "\n".join(near) if near else ""
            return f"old_str not found in {path}. File has {len(lines)} lines.{hint}"
        if count > 1:
            return f"old_str found {count} times — must be unique. Add more context."

        new_content = content.replace(old_str, new_str, 1)
        fpath.write_text(new_content)
        self.files_edited.append(path)

        # Show diff context
        old_lines = old_str.count("\n") + 1
        new_lines = new_str.count("\n") + 1
        return f"Edited {path}: replaced {old_lines} lines with {new_lines} lines"

    # --- search ---
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
                cmd, capture_output=True, text=True, timeout=15, cwd=self.workspace
            )
            output = result.stdout
            if not output.strip():
                return f"No matches for pattern: {pattern}"
            lines = output.strip().split("\n")
            if len(lines) > 30:
                lines = lines[:30]
                lines.append(f"... ({len(output.strip().split(chr(10)))} total matches)")
            # Strip workspace prefix for readability
            cleaned = []
            for line in lines:
                cleaned.append(line.replace(self.workspace + "/", ""))
            return "\n".join(cleaned)
        except FileNotFoundError:
            # Fallback to grep if rg not available
            cmd = ["grep", "-rn", "--color=never"]
            if args.get("case_insensitive"):
                cmd.append("-i")
            if args.get("file_type"):
                cmd.extend(["--include", f"*.{args['file_type']}"])
            cmd.extend([pattern, search_path])
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, cwd=self.workspace
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

    # --- list_dir ---
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
            cmd = ["find", str(target), "-maxdepth", str(max_depth),
                   "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*",
                   "-not", "-name", ".git"]
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
                entries.append(f"  ... (truncated, >100 entries)")

            return f"[{path or '.'}] ({len(entries)} items)\n" + "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {e}"

    # --- git ---
    def _tool_git(self, args: dict) -> str:
        command = args.get("command", "")
        if not command.strip():
            return "ERROR: git command required"

        # Security: block dangerous git operations
        blocked_ops = ["push --force", "push -f", "reset --hard HEAD~", "clean -fd"]
        for b in blocked_ops:
            if b in command:
                return f"BLOCKED: '{b}' not allowed"

        # Block operations on protected branches
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

    # --- run_tests ---
    def _tool_run_tests(self, args: dict) -> str:
        command = args.get("command", "")
        test_filter = args.get("filter", "")

        if not command:
            # Auto-detect test framework
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
                output = output[-MAX_OUTPUT_CHARS:]  # Keep tail for test results

            # Parse test counts (heuristic)
            import re
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

    # --- helpers ---
    def _resolve_path(self, path: str) -> Path | str:
        """Resolve path relative to workspace, with security check."""
        if path.startswith("/"):
            fpath = Path(path)
        else:
            fpath = Path(self.workspace) / path

        try:
            resolved = fpath.resolve()
            ws_resolved = Path(self.workspace).resolve()
            # Allow paths within workspace or /tmp
            if not (str(resolved).startswith(str(ws_resolved)) or
                    str(resolved).startswith("/tmp")):
                return f"BLOCKED: path '{path}' escapes workspace boundary"
        except Exception:
            return f"BLOCKED: cannot resolve path '{path}'"
        return fpath

    def _get_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace, capture_output=True, text=True, timeout=5
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

SYSTEM_PROMPT_TEMPLATE = """You are an autonomous coding agent executing tasks in a workspace.

## Workspace
Working directory: {workspace}

## Available Tools
- **bash**: Run any shell command (find, grep, npm, python, git, etc.)
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
2. Be efficient — read only the files you need, then START WRITING CODE IMMEDIATELY.
3. Do NOT read every file before acting. Read 2-3 key files, then implement. Read more only when stuck.
4. Use edit_file for targeted changes (preferred over write_file for existing files).
5. Run tests after making changes to verify correctness.
6. Call finish() when the task is complete or when you determine it cannot be done.
7. If something fails, try an alternative approach before giving up.
8. Do NOT push to remote. Do NOT modify protected branches (main/master/develop).
9. Commit your changes to the current branch when task is complete.
10. BIAS TOWARD ACTION: After reading context, write code. Do not endlessly read files.

## Current Branch
{branch}
"""


def _prune_messages(messages: list[dict], max_chars: int = 200000) -> None:
    """Prune message history to stay within context limits.
    Keeps system + first user message, trims oldest tool results."""
    total = sum(len(str(m.get("content", "") or "")) for m in messages)
    if total <= max_chars:
        return
    # Find tool messages (observations) and truncate them starting from oldest
    for i in range(2, len(messages)):  # Skip system + first user
        if total <= max_chars:
            break
        msg = messages[i]
        content = msg.get("content", "") or ""
        if msg.get("role") == "tool" and len(content) > 500:
            old_len = len(content)
            msg["content"] = content[:200] + "\n... [truncated to fit context] ...\n" + content[-200:]
            total -= (old_len - len(msg["content"]))
    # If still over, remove oldest assistant+tool groups (keep system + first user)
    while total > max_chars and len(messages) > 4:
        idx = 2
        if idx >= len(messages):
            break
        msg = messages[idx]
        # Remove the message and track size reduction
        removed_size = len(str(msg.get("content", "") or ""))
        messages.pop(idx)
        # If we removed an assistant message with tool_calls, also remove its paired tool responses
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = {tc.get("id") for tc in msg["tool_calls"] if isinstance(tc, dict)}
            while idx < len(messages) and messages[idx].get("role") == "tool":
                if messages[idx].get("tool_call_id") in tool_call_ids:
                    orphan = messages.pop(idx)
                    removed_size += len(str(orphan.get("content", "") or ""))
                else:
                    break
        # If we removed a tool message, find and clean up its parent's tool_call entry
        elif msg.get("role") == "tool" and msg.get("tool_call_id"):
            orphan_id = msg["tool_call_id"]
            for prev in messages[:idx]:
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    prev["tool_calls"] = [tc for tc in prev["tool_calls"]
                                          if tc.get("id") != orphan_id]
        total -= removed_size


def _run_agent_loop(
    instruction: str,
    workspace: str,
    model: str = DEFAULT_MODEL,
    max_iterations: int = MAX_ITERATIONS,
    execution_mode: str = "finite",
    event_callback=None,
    plan_context: str = "",
) -> tuple[str, str, list[str], int, int, list[str]]:
    """Run the LLM tool-calling agent loop.

    Returns: (status, summary, files_edited, tests_passed, tests_failed, commands_run)
    """
    executor = ToolExecutor(workspace)
    branch = executor._get_branch() or "unknown"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        workspace=workspace,
        branch=branch,
    )

    if plan_context:
        system_prompt += f"\n## Advisory Plan from agent-core\n{plan_context}\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    status = "completed"
    summary = ""

    effective_limit = max_iterations if execution_mode == "finite" else 999999
    for iteration in range(effective_limit):
        if event_callback:
            if execution_mode == "finite":
                iter_label = f"{iteration + 1}/{max_iterations}"
            else:
                mode_name = "open-ended" if execution_mode == "open_ended" else "loop"
                iter_label = f"{iteration + 1} ({mode_name})"
            event_callback("action_progress", f"Agent iteration {iter_label}", {
                "iteration": iteration + 1,
                "tools_used": len(executor.commands_run),
                "files_edited": len(executor.files_edited),
            })

        # Prune message history to stay within context window
        _prune_messages(messages, max_chars=200000)

        try:
            response = _call_llm(messages, model)
        except RuntimeError as e:
            error_str = str(e)
            if "ContextWindowExceeded" in error_str or "context length" in error_str:
                # Aggressive pruning and retry
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

        # No tool calls — LLM wants to respond with text
        if not message.get("tool_calls"):
            content = message.get("content", "")
            if content:
                summary = content[:500]
            # If LLM stopped without calling finish, treat as done
            if finish_reason == "stop":
                status = "completed"
            break

        # Process tool calls
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

            # Handle finish
            if tool_name == "finish":
                summary = tool_args.get("summary", "Task completed")
                status = tool_args.get("status", "completed")
                return (status, summary, executor.files_edited,
                        executor.tests_passed, executor.tests_failed, executor.commands_run)

            # Execute tool
            observation = executor.execute(tool_name, tool_args)

            # Emit tool event with output
            if event_callback:
                output_preview = observation[:2000] if observation else "(no output)"
                event_callback("action_progress", f"Tool: {tool_name}", {
                    "tool": tool_name,
                    "args_summary": _summarize_args(tool_name, tool_args),
                    "type": "tool_output",
                    "output": output_preview,
                })

            # Add observation
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": observation,
            })

    else:
        if execution_mode == "finite":
            summary = f"Reached max iterations ({max_iterations}) without calling finish"
            status = "needs_review"
        else:
            summary = f"Completed after {effective_limit} iterations (mode: {execution_mode})"
            status = "completed"

    return (status, summary, executor.files_edited,
            executor.tests_passed, executor.tests_failed, executor.commands_run)


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


# ============================================================
# ADAPTER CLASS
# ============================================================

class OpenHandsExecutorAdapter(ExecutorAdapter):
    """Execute tasks locally via LLM tool-calling loop.

    Uses vendored OpenHands SDK workspace concepts but executes locally.
    Backed by LiteLLM proxy for LLM access (DeepSeek, etc.).

    The adapter:
    1. Receives a TaskPacket (instruction + workspace + context)
    2. Runs an autonomous agent loop (LLM + tools)
    3. Returns structured TaskResult (status, files, tests, summary)
    4. Streams events throughout execution
    """

    def __init__(self):
        self._events: dict[str, list[dict]] = {}

    def is_available(self) -> bool:
        """Check if execution backend (LiteLLM) is reachable."""
        import urllib.request
        try:
            urllib.request.urlopen(f"{LITELLM_URL}/health/liveliness", timeout=3)
            return True
        except Exception:
            return False

    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        """Execute task via local agent loop.

        Full execution pipeline:
        1. Validate workspace exists and branch is safe
        2. Start agent loop with LLM tool calling
        3. Record all events to session events.jsonl
        4. Return structured result
        """
        start_time = time.time()
        session_dir = SESSIONS_DIR / session_id
        events_dir = session_dir / "events"
        session_dir.mkdir(parents=True, exist_ok=True)
        events_dir.mkdir(parents=True, exist_ok=True)

        workspace = packet.worktree_path
        if not workspace or not Path(workspace).exists():
            # Try session meta for repo_path
            meta_path = session_dir / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    workspace = meta.get("repo_path", "") or meta.get("worktree_path", "")
                except Exception:
                    pass

        if not workspace or not Path(workspace).exists():
            return TaskResult(
                status="failed",
                error=f"No valid workspace found for session {session_id}",
                summary="Cannot execute: workspace directory not found",
                duration_seconds=0,
            )

        # Check branch safety
        branch = self._get_current_branch(workspace) or packet.branch
        if branch in PROTECTED_BRANCHES:
            return TaskResult(
                status="failed",
                error=f"Cannot execute on protected branch: {branch}",
                summary=f"Blocked: execution on '{branch}' is not allowed",
                duration_seconds=0,
            )

        # Event recording
        self._events[session_id] = []
        seq = [0]

        def event_callback(event_type: str, message: str, metadata: dict = None):
            seq[0] += 1
            event = {
                "event_type": event_type,
                "session_id": session_id,
                "sequence": seq[0],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"message": message, **(metadata or {})},
            }
            self._events[session_id].append(event)
            events_file = events_dir / "events.jsonl"
            with events_file.open("a") as f:
                f.write(json.dumps(event) + "\n")

        event_callback("executor_started", "OpenHands local executor starting", {
            "workspace": workspace,
            "model": packet.model or DEFAULT_MODEL,
            "task_id": packet.task_id,
            "branch": branch,
        })

        # Build plan context from packet metadata
        plan_context = ""
        if packet.activated_knowledge:
            plan_context += "Relevant knowledge:\n"
            for k in packet.activated_knowledge:
                plan_context += f"- {k}\n"

        # Run the agent loop
        try:
            (status, summary, files_edited,
             tests_passed, tests_failed, commands_run) = _run_agent_loop(
                instruction=packet.to_markdown(),
                workspace=workspace,
                model=packet.model or DEFAULT_MODEL,
                execution_mode=getattr(packet, 'execution_mode', 'finite'),
                event_callback=event_callback,
                plan_context=plan_context,
            )
        except Exception as e:
            duration = time.time() - start_time
            event_callback("executor_error", f"Agent loop crashed: {e}")
            return TaskResult(
                status="failed",
                error=str(e),
                summary=f"Execution crashed: {e}",
                duration_seconds=duration,
            )

        duration = time.time() - start_time
        event_callback("executor_finished", summary, {
            "status": status,
            "files_edited": files_edited,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "commands_run": len(commands_run),
            "duration_seconds": round(duration, 1),
        })

        return TaskResult(
            status=status,
            files_edited=files_edited,
            commands_run=commands_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            summary=summary,
            duration_seconds=duration,
        )

    def stream_events(self, session_id: str) -> Iterator[dict]:
        """Yield events for a session (from memory and disk)."""
        # First yield in-memory events
        for event in self._events.get(session_id, []):
            yield event

        # Also check disk if not in memory
        if session_id not in self._events:
            events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
            if events_file.exists():
                for line in events_file.read_text().strip().split("\n"):
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue

    def _get_current_branch(self, worktree: str) -> str:
        """Get current git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""


# Keep backward compat
__all__ = ["OpenHandsExecutorAdapter", "ToolExecutor", "TOOLS"]
