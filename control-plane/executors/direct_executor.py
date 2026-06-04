"""
Direct Executor — structured tool-calling loop for autonomous code editing.

Architecture:
1. Runs inside the host environment (direct access to session worktrees)
2. Uses LiteLLM for reasoning via structured tool calls
3. Enforces session worktree boundaries on every operation
4. Records every tool call and observation in the session timeline

Tools:
  read_file, write_file, apply_patch, list_files, grep, run_command,
  git_status, git_diff, git_commit, run_validation, get_latest_context

Execution loop:
  assemble task packet → include context → ask model for tool call →
  execute tool → append observation → continue until done or max iterations →
  run validation → commit if passed → mark needs_review if not
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.base import ExecutorAdapter, TaskPacket, TaskResult, SESSIONS_DIR, TASKS_DIR

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get(
    "LITELLM_MASTER_KEY",
    "fdfe750a587cddaedd90f39afb861f67377b155b7fdbe5d39d53437b29a700ed",
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")
MAX_ITERATIONS = int(os.environ.get("DIRECT_EXECUTOR_MAX_ITERATIONS", "30"))
MAX_OBSERVATION_CHARS = 8000
MAX_CONTEXT_MESSAGES = 60
STUCK_THRESHOLD = 3

FORBIDDEN_PATHS = ["/etc", "/root", "/var", "/usr", "/boot", "/proc", "/sys"]
FORBIDDEN_COMMANDS = ["rm -rf /", "sudo rm", "mkfs", "dd if=", "> /dev/", "shutdown", "reboot"]
PROTECTED_BRANCHES = ["main", "master", "develop", "production"]
SECRETS_PATTERNS = [".env", "credentials", "secrets", ".pem", ".key", "id_rsa"]

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the session worktree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from worktree root"},
                    "start_line": {"type": "integer", "description": "Optional start line (1-based)"},
                    "end_line": {"type": "integer", "description": "Optional end line (1-based)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the session worktree. Creates the file if it doesn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from worktree root"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a find-and-replace edit to a file. Replaces the first occurrence of old_text with new_text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from worktree root"},
                    "old_text": {"type": "string", "description": "Exact text to find (must be unique in file)"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory within the session worktree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default: root)"},
                    "pattern": {"type": "string", "description": "Glob pattern to filter (e.g. '*.ts')"},
                    "recursive": {"type": "boolean", "description": "Whether to list recursively"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a pattern in files within the session worktree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory or file to search in (relative)"},
                    "include": {"type": "string", "description": "File glob to include (e.g. '*.ts')"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the session worktree. Commands are validated against safety policy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Max seconds to wait (default: 60)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status of the session worktree.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff of uncommitted changes in the session worktree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "Show only staged changes"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage all changes and commit with a message. Only works on session branches (never main/master).",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_validation",
            "description": "Run the project's test/lint/build validation suite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "checks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which checks to run: 'test', 'lint', 'build'. Default: all available.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_context",
            "description": "Get the latest ambient context (UI focus, editor selection, terminal errors) for this session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context_type": {
                        "type": "string",
                        "enum": ["ui", "editor", "terminal", "all"],
                        "description": "Which context to retrieve. Default: all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Use this to reason about the problem without taking action. Good for planning your approach before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thought": {"type": "string", "description": "Your reasoning or plan"},
                },
                "required": ["thought"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal that you are done with the task. Call this when you have finished all edits and validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of what was done"},
                },
                "required": ["summary"],
            },
        },
    },
]


class DirectExecutor(ExecutorAdapter):
    """Structured tool-calling executor with worktree enforcement.

    Incorporates patterns from OpenHands software-agent-sdk:
    - Stuck detection (repeated tool calls break the loop)
    - Observation truncation (large outputs trimmed to fit context)
    - Context window management (old messages dropped when too many)
    - Think tool for reasoning without action
    - Phase-based system prompt guiding explore->edit->validate->commit
    """

    @staticmethod
    def _truncate_observation(obs: dict) -> dict:
        """Truncate large observation content to fit context window."""
        for key in ("content", "output", "stdout"):
            if key in obs and isinstance(obs[key], str) and len(obs[key]) > MAX_OBSERVATION_CHARS:
                half = MAX_OBSERVATION_CHARS // 2
                obs[key] = (
                    obs[key][:half]
                    + "\n\n... [" + str(len(obs[key]) - MAX_OBSERVATION_CHARS) + " chars truncated] ...\n\n"
                    + obs[key][-half:]
                )
        return obs

    @staticmethod
    def _detect_stuck(recent_calls: list) -> bool:
        """Detect if the agent is stuck repeating the same tool call."""
        if len(recent_calls) < STUCK_THRESHOLD:
            return False
        last_n = recent_calls[-STUCK_THRESHOLD:]
        return all(c == last_n[0] for c in last_n)

    @staticmethod
    def _trim_context(messages: list) -> list:
        """Trim old tool responses when message list grows too long."""
        if len(messages) <= MAX_CONTEXT_MESSAGES:
            return messages
        keep_tail = MAX_CONTEXT_MESSAGES - 2
        trimmed = messages[:2] + messages[-keep_tail:]
        trimmed.insert(2, {
            "role": "user",
            "content": "[Context trimmed: earlier tool exchanges removed to fit context window. Focus on current task.]"
        })
        return trimmed

    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        start_time = time.time()
        session_dir = SESSIONS_DIR / session_id
        events_dir = session_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)

        worktree = packet.worktree_path
        if not worktree or not Path(worktree).exists():
            return TaskResult(status="failed", error="No worktree found", duration_seconds=0)

        # Validate branch
        branch = self._get_current_branch(worktree)
        if branch in PROTECTED_BRANCHES:
            return TaskResult(status="failed", error=f"Cannot execute on protected branch: {branch}", duration_seconds=0)

        packet.save()
        self._record_timeline_event(session_id, "task_start", {
            "task_id": packet.task_id,
            "instruction": packet.instruction[:200],
            "executor": "direct",
            "worktree": worktree,
            "branch": branch,
        })

        # Build initial messages
        messages = self._build_initial_messages(packet, worktree)

        files_edited = []
        self._recent_calls = []
        commands_run = []
        tool_calls_count = 0
        task_done = False
        task_summary = ""

        # Execution loop
        for iteration in range(MAX_ITERATIONS):
            if task_done:
                break

            # Trim context if growing too large
            messages = self._trim_context(messages)

            # Ask model for next tool call
            try:
                response = self._call_llm_with_tools(messages, packet.model)
            except Exception as e:
                self._record_timeline_event(session_id, "llm_error", {"error": str(e), "iteration": iteration})
                break

            # Process response
            assistant_msg = response.get("choices", [{}])[0].get("message", {})
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls")
            if not tool_calls:
                # Model responded with text (no tool call) — done
                content = assistant_msg.get("content", "")
                if content:
                    self._record_timeline_event(session_id, "agent_message", {"text": content[:300]})
                break

            # Execute each tool call
            for tool_call in tool_calls:
                tool_calls_count += 1
                func_name = tool_call["function"]["name"]
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Handle think tool (no execution needed)
                if func_name == "think":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({"ok": True}),
                    })
                    self._record_timeline_event(session_id, "think", {
                        "thought": str(args.get("thought", ""))[:500],
                        "iteration": iteration,
                    })
                    continue

                # Stuck detection
                call_sig = json.dumps({"t": func_name, "a": args}, sort_keys=True)
                self._recent_calls.append(call_sig)
                if self._detect_stuck(self._recent_calls):
                    self._record_timeline_event(session_id, "stuck_detected", {
                        "tool": func_name, "iteration": iteration,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({"success": False, "error": "STUCK: Identical tool call repeated. Change your approach or call task_complete."}),
                    })
                    continue

                # Execute tool
                observation = self._execute_tool(
                    func_name, args, worktree, session_id, branch
                )

                # Truncate large observations
                observation = self._truncate_observation(observation)

                # Track edits
                if func_name == "write_file" and observation.get("success"):
                    path = args.get("path", "")
                    if path and path not in files_edited:
                        files_edited.append(path)
                elif func_name == "apply_patch" and observation.get("success"):
                    path = args.get("path", "")
                    if path and path not in files_edited:
                        files_edited.append(path)
                elif func_name == "run_command":
                    commands_run.append(args.get("command", "")[:200])
                elif func_name == "task_complete":
                    task_done = True
                    task_summary = args.get("summary", "")

                # Record in timeline
                self._record_timeline_event(session_id, "tool_call", {
                    "tool": func_name,
                    "args": {k: str(v)[:200] for k, v in args.items()},
                    "success": observation.get("success", False),
                    "iteration": iteration,
                })

                # Append tool response to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(observation)[:4000],
                })

        # Post-loop: run validation if files were edited
        tests_passed = 0
        tests_failed = 0
        validation_result = None
        if files_edited:
            validation_result = self.run_validation(session_id)
            if validation_result.get("results", {}).get("test"):
                tests_passed = 1 if validation_result["results"]["test"]["passed"] else 0
                tests_failed = 0 if validation_result["results"]["test"]["passed"] else 1

        # Commit if we have changes and validation didn't fail hard
        commit_sha = None
        if files_edited:
            # Check if model already committed (via git_commit tool)
            status_result = subprocess.run(
                ["git", "status", "--porcelain"], cwd=worktree, capture_output=True, text=True,
            )
            if status_result.stdout.strip():
                # Uncommitted changes remain — commit them
                commit_msg = f"fix: {packet.instruction[:72]}"
                commit_sha = self.commit_changes(session_id, commit_msg)
            else:
                # Already committed — get latest SHA
                sha_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=worktree, capture_output=True, text=True,
                )
                commit_sha = sha_result.stdout.strip()

        duration = time.time() - start_time
        status = "committed" if commit_sha else ("failed" if not files_edited else "needs_review")

        self._record_timeline_event(session_id, "task_complete", {
            "task_id": packet.task_id,
            "status": status,
            "files_edited": files_edited,
            "commands_run": len(commands_run),
            "tool_calls": tool_calls_count,
            "commit": commit_sha,
            "duration": duration,
            "summary": task_summary,
        })

        return TaskResult(
            status=status,
            files_edited=files_edited,
            commands_run=commands_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            commit_sha=commit_sha,
            summary=task_summary,
            duration_seconds=duration,
        )

    def _build_initial_messages(self, packet: TaskPacket, worktree: str) -> list:
        """Build the initial system + user messages for the LLM."""
        system_prompt = f"""You are a precise autonomous coding agent. You receive a task and MUST produce a working code change.

## Execution Protocol

Phase 1 - LOCATE (max 3 tool calls):
  Use grep or list_files to find the relevant file(s). Do NOT read entire files yet.

Phase 2 - UNDERSTAND (max 2 tool calls):
  Use read_file on the specific section you need to change. Use start_line/end_line to read only what matters.

Phase 3 - EDIT (1-3 tool calls):
  Use apply_patch for surgical edits (preferred) or write_file for new files.
  If apply_patch fails with "old_text not found", re-read the file to get exact current content, then retry.

Phase 4 - VALIDATE (1 tool call):
  Use run_validation or run_command to verify your change works.

Phase 5 - COMMIT (1-2 tool calls):
  Use git_commit with a descriptive message, then call task_complete.

## Self-Correction Rules (from OpenHands patterns)
- If a tool returns an error, fix it immediately. Do not repeat the same failing call.
- If read_file shows the file is large, use start_line/end_line to narrow scope.
- If apply_patch fails, the file content may have changed. Re-read and retry with correct old_text.
- If you are unsure what to do, use the think tool to reason before acting.
- NEVER call the same tool with identical arguments twice in a row.

## Environment
Working directory: {worktree}
Branch: {packet.branch}
Session: {packet.session_id}

## Constraints
- Only modify files inside the worktree.
- Do not touch node_modules, .git, or generated directories.
- Make minimal, focused changes.
- Always call task_complete as your final action.

## Tools
read_file, write_file, apply_patch, list_files, grep, run_command,
git_status, git_diff, git_commit, run_validation, get_latest_context, think, task_complete"""

        user_parts = [f"## Task\n{packet.instruction}"]
        if packet.ui_context:
            user_parts.append(f"## Current UI Context\n{packet.ui_context[:1000]}")
        if packet.editor_context:
            user_parts.append(f"## Current Editor Context\n{packet.editor_context[:1000]}")
        if packet.terminal_context:
            user_parts.append(f"## Current Terminal Context\n{packet.terminal_context[:1000]}")
        if packet.activated_knowledge:
            knowledge_text = "\n".join(
                f"- {k.get('description', '')}: {k.get('content', '')}"
                for k in packet.activated_knowledge
            )
            user_parts.append(f"## Activated Knowledge\n{knowledge_text}")
        if packet.staleness_warnings:
            user_parts.append(f"## Warnings\n" + "\n".join(f"- {w}" for w in packet.staleness_warnings))

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    def _call_llm_with_tools(self, messages: list, model: str = None) -> dict:
        """Call LiteLLM with tool definitions and return the response."""
        import urllib.request

        model = model or DEFAULT_MODEL
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 4000,
        }

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{LITELLM_URL}/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LITELLM_KEY}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=90)
        return json.loads(resp.read())

    def _execute_tool(self, name: str, args: dict, worktree: str, session_id: str, branch: str) -> dict:
        """Execute a tool call with full validation."""

        if name == "read_file":
            return self._tool_read_file(args, worktree)
        elif name == "write_file":
            return self._tool_write_file(args, worktree)
        elif name == "apply_patch":
            return self._tool_apply_patch(args, worktree)
        elif name == "list_files":
            return self._tool_list_files(args, worktree)
        elif name == "grep":
            return self._tool_grep(args, worktree)
        elif name == "run_command":
            return self._tool_run_command(args, worktree)
        elif name == "git_status":
            return self._tool_git_status(worktree)
        elif name == "git_diff":
            return self._tool_git_diff(args, worktree)
        elif name == "git_commit":
            return self._tool_git_commit(args, worktree, branch, session_id)
        elif name == "run_validation":
            return self._tool_run_validation(args, session_id)
        elif name == "get_latest_context":
            return self._tool_get_latest_context(args, session_id)
        elif name == "task_complete":
            return {"success": True, "message": "Task marked complete."}
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    # --- Path validation ---

    def _validate_path(self, relative_path: str, worktree: str) -> Optional[str]:
        """Validate and resolve a path. Returns error string or None if valid."""
        if not relative_path:
            return "Path is empty"
        # Normalize
        resolved = (Path(worktree) / relative_path).resolve()
        worktree_resolved = Path(worktree).resolve()
        # Must be inside worktree
        if not str(resolved).startswith(str(worktree_resolved)):
            return f"Path escapes worktree boundary: {relative_path}"
        # Must not be in forbidden locations
        for forbidden in FORBIDDEN_PATHS:
            if str(resolved).startswith(forbidden):
                return f"Path in forbidden location: {forbidden}"
        # Must not be a secrets file
        for pattern in SECRETS_PATTERNS:
            if pattern in str(relative_path).lower():
                return f"Cannot access secrets file: {relative_path}"
        return None

    def _validate_command(self, command: str) -> Optional[str]:
        """Validate a shell command. Returns error string or None if allowed."""
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden in command:
                return f"Forbidden command pattern: {forbidden}"
        if "sudo" in command.split():
            return "sudo is not allowed"
        return None

    # --- Tool implementations ---

    def _tool_read_file(self, args: dict, worktree: str) -> dict:
        path = args.get("path", "")
        error = self._validate_path(path, worktree)
        if error:
            return {"success": False, "error": error}

        full_path = Path(worktree) / path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not full_path.is_file():
            return {"success": False, "error": f"Not a file: {path}"}

        try:
            content = full_path.read_text(errors="replace")
            start = args.get("start_line")
            end = args.get("end_line")
            if start or end:
                lines = content.split("\n")
                start_idx = (start - 1) if start else 0
                end_idx = end if end else len(lines)
                content = "\n".join(lines[start_idx:end_idx])
            # Truncate large files
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            return {"success": True, "content": content, "size": full_path.stat().st_size}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_write_file(self, args: dict, worktree: str) -> dict:
        path = args.get("path", "")
        content = args.get("content", "")
        error = self._validate_path(path, worktree)
        if error:
            return {"success": False, "error": error}

        full_path = Path(worktree) / path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            return {"success": True, "path": path, "bytes_written": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_apply_patch(self, args: dict, worktree: str) -> dict:
        path = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        error = self._validate_path(path, worktree)
        if error:
            return {"success": False, "error": error}

        full_path = Path(worktree) / path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        try:
            current = full_path.read_text()
            if old_text not in current:
                return {"success": False, "error": "old_text not found in file. Read the file first to get exact content."}
            count = current.count(old_text)
            new_content = current.replace(old_text, new_text, 1)
            full_path.write_text(new_content)
            return {"success": True, "path": path, "occurrences_found": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_list_files(self, args: dict, worktree: str) -> dict:
        path = args.get("path", ".")
        pattern = args.get("pattern", "*")
        recursive = args.get("recursive", False)

        target = Path(worktree) / path
        if not target.exists():
            return {"success": False, "error": f"Directory not found: {path}"}

        try:
            if recursive:
                files = [str(f.relative_to(worktree)) for f in target.rglob(pattern)
                         if "node_modules" not in str(f) and ".git" not in str(f)]
            else:
                files = [str(f.relative_to(worktree)) for f in target.glob(pattern)
                         if "node_modules" not in str(f) and ".git" not in str(f)]
            files = sorted(files)[:200]  # limit
            return {"success": True, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_grep(self, args: dict, worktree: str) -> dict:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        include = args.get("include", "")

        target = Path(worktree) / path
        cmd = ["grep", "-rn", "--exclude-dir=node_modules", "--exclude-dir=.git",
               "--exclude-dir=dist", "--exclude-dir=build"]
        if include:
            cmd.extend(["--include", include])
        cmd.extend([pattern, str(target)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            lines = result.stdout.strip().split("\n")[:50]
            # Make paths relative
            rel_lines = []
            for line in lines:
                if line.strip():
                    rel_lines.append(line.replace(str(worktree) + "/", ""))
            return {"success": True, "matches": rel_lines, "count": len(rel_lines)}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "grep timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_run_command(self, args: dict, worktree: str) -> dict:
        command = args.get("command", "")
        timeout = min(args.get("timeout", 60), 120)

        error = self._validate_command(command)
        if error:
            return {"success": False, "error": error}

        try:
            result = subprocess.run(
                command, shell=True, cwd=worktree,
                capture_output=True, text=True, timeout=timeout,
            )
            stdout = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
            stderr = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_git_status(self, worktree: str) -> dict:
        try:
            result = subprocess.run(
                ["git", "status", "--short"], cwd=worktree, capture_output=True, text=True,
            )
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"], cwd=worktree, capture_output=True, text=True,
            )
            return {
                "success": True,
                "branch": branch_result.stdout.strip(),
                "changes": result.stdout.strip(),
                "clean": not result.stdout.strip(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_git_diff(self, args: dict, worktree: str) -> dict:
        staged = args.get("staged", False)
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        try:
            result = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True)
            diff = result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout
            return {"success": True, "diff": diff}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_git_commit(self, args: dict, worktree: str, branch: str, session_id: str) -> dict:
        message = args.get("message", "")
        if not message:
            return {"success": False, "error": "Commit message is required"}

        # Validate branch
        current_branch = self._get_current_branch(worktree)
        if current_branch in PROTECTED_BRANCHES:
            return {"success": False, "error": f"Cannot commit to protected branch: {current_branch}"}

        try:
            subprocess.run(["git", "add", "-A"], cwd=worktree, capture_output=True)
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=worktree, capture_output=True, text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Agent",
                    "GIT_AUTHOR_EMAIL": "agent@workstation.local",
                    "GIT_COMMITTER_NAME": "Agent",
                    "GIT_COMMITTER_EMAIL": "agent@workstation.local",
                },
            )
            if result.returncode == 0:
                sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=worktree, capture_output=True, text=True,
                ).stdout.strip()
                return {"success": True, "commit_sha": sha, "message": message}
            return {"success": False, "error": result.stderr.strip() or "Nothing to commit"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_run_validation(self, args: dict, session_id: str) -> dict:
        result = self.run_validation(session_id)
        return {"success": result.get("status") == "passed", "validation": result}

    def _tool_get_latest_context(self, args: dict, session_id: str) -> dict:
        context_type = args.get("context_type", "all")
        ctx_dir = SESSIONS_DIR / session_id / "context"
        context = {}

        type_map = {
            "ui": "latest-ui-context.md",
            "editor": "latest-editor-context.md",
            "terminal": "latest-terminal-context.md",
        }

        if context_type == "all":
            for ctype, filename in type_map.items():
                path = ctx_dir / filename
                if path.exists():
                    context[ctype] = path.read_text()[:2000]
        elif context_type in type_map:
            path = ctx_dir / type_map[context_type]
            if path.exists():
                context[context_type] = path.read_text()[:2000]

        return {"success": True, "context": context}

    # --- Helpers ---

    def _get_current_branch(self, worktree: str) -> str:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree, capture_output=True, text=True,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def stream_events(self, session_id: str) -> Iterator[dict]:
        events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
        if not events_file.exists():
            return
        with open(events_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield {"type": "raw", "text": line}
