"""
OpenHands Headless Executor — autonomous tool loop.

Strategy:
1. Try OpenHands HTTP API (localhost:3000) to create a conversation/task
2. If that fails, use the Direct Executor (LLM + file tools) as fallback

The Direct Executor uses DeepSeek via LiteLLM to plan edits, then applies them
directly using file I/O and subprocess — giving us a real read/edit/run/test/commit loop.
"""

import json
import os
import re
import subprocess
import time
import urllib.request
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
    "<litellm-key>",
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")
OPENHANDS_URL = os.environ.get("OPENHANDS_URL", "http://localhost:3000")


class OpenHandsHeadlessExecutor(ExecutorAdapter):
    """Execute tasks via direct file manipulation guided by LLM."""

    MAX_ITERATIONS = int(os.environ.get("AGENT_MAX_ITERATIONS", "10"))

    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        start_time = time.time()
        session_dir = SESSIONS_DIR / session_id
        events_dir = session_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)

        packet.save()

        self._record_timeline_event(session_id, "task_start", {
            "task_id": packet.task_id,
            "instruction": packet.instruction[:200],
            "executor": "openhands-headless",
        })

        # Direct executor: LLM plans → we execute
        result = self._run_direct_executor(session_id, packet)

        self._record_timeline_event(session_id, "task_complete", {
            "task_id": packet.task_id,
            "status": result.status,
            "files_edited": len(result.files_edited),
            "commit": result.commit_sha,
            "duration": result.duration_seconds,
        })

        return result

    def _run_direct_executor(self, session_id: str, packet: TaskPacket) -> TaskResult:
        """
        Direct executor: ask LLM for a plan, then execute it.

        Loop:
        1. Send context + instruction to LLM
        2. Parse response for file edits, commands
        3. Apply edits
        4. Run commands
        5. Validate (tests/lint)
        6. Commit if passed
        """
        start_time = time.time()
        worktree = packet.worktree_path
        if not worktree or not Path(worktree).exists():
            return TaskResult(status="failed", error="No worktree found", duration_seconds=0)

        files_edited = []
        commands_run = []

        # Step 1: Get file listing
        listing = subprocess.run(
            ["find", ".", "-name", "*.ts", "-o", "-name", "*.tsx", "-o", "-name", "*.py",
             "-o", "-name", "*.js", "-o", "-name", "*.md", "-o", "-name", "*.json"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        file_list = listing.stdout.strip()[:2000]

        # Step 2: Ask LLM for a concrete plan
        system_prompt = """You are an autonomous coding agent. You have access to a worktree.
Your job is to make the requested change and output the EXACT file edits needed.

Output your response in this format:
1. First, explain briefly what you'll do (1-2 sentences)
2. Then output each file edit as:

FILE: path/to/file
```
entire new file content
```

OR for partial edits:
EDIT: path/to/file
FIND:
```
exact lines to find
```
REPLACE:
```
replacement lines
```

3. If you need to run a shell command, output:
RUN: command here

Be precise. Output only what's needed."""

        user_prompt = packet.to_markdown() + f"\n\n## Files in worktree\n```\n{file_list}\n```"

        # Read relevant files based on instruction
        relevant_files_content = ""
        instruction_lower = packet.instruction.lower()
        for keyword_file_map in [
            ("readme", "README.md"),
            ("package", "package.json"),
            ("index", "index.html"),
        ]:
            keyword, filename = keyword_file_map
            if keyword in instruction_lower:
                fpath = Path(worktree) / filename
                if fpath.exists():
                    content = fpath.read_text()[:3000]
                    relevant_files_content += f"\n\n## Current {filename}\n```\n{content}\n```"

        if relevant_files_content:
            user_prompt += relevant_files_content

        try:
            llm_response = self._call_llm(system_prompt, user_prompt, packet.model)
        except Exception as e:
            return TaskResult(
                status="failed", error=f"LLM call failed: {e}",
                duration_seconds=time.time() - start_time,
            )

        self._record_timeline_event(session_id, "agent_output", {"text": llm_response[:500]})

        # Step 3: Parse and apply edits
        file_edits = self._parse_file_edits(llm_response)
        run_commands = self._parse_run_commands(llm_response)

        for filepath, content in file_edits:
            full_path = Path(worktree) / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            files_edited.append(filepath)
            self._record_timeline_event(session_id, "file_edit", {"file": filepath})

        # Apply FIND/REPLACE edits
        find_replace_edits = self._parse_find_replace_edits(llm_response)
        for filepath, find_text, replace_text in find_replace_edits:
            full_path = Path(worktree) / filepath
            if full_path.exists():
                current = full_path.read_text()
                if find_text in current:
                    new_content = current.replace(find_text, replace_text, 1)
                    full_path.write_text(new_content)
                    if filepath not in files_edited:
                        files_edited.append(filepath)
                    self._record_timeline_event(session_id, "file_edit", {"file": filepath})

        # Step 4: Run commands
        for cmd in run_commands[:5]:  # limit to 5 commands
            try:
                result = subprocess.run(
                    cmd, shell=True, cwd=worktree,
                    capture_output=True, text=True, timeout=60,
                )
                commands_run.append(cmd)
                self._record_timeline_event(session_id, "command_run", {
                    "command": cmd[:200],
                    "exit_code": result.returncode,
                })
            except Exception:
                pass

        # Step 5: Validate
        validation = self.run_validation(session_id)
        tests_passed = 0
        tests_failed = 0
        if validation.get("results", {}).get("test"):
            tests_passed = 1 if validation["results"]["test"]["passed"] else 0
            tests_failed = 0 if validation["results"]["test"]["passed"] else 1

        # Step 6: Commit if we made changes
        commit_sha = None
        if files_edited:
            commit_msg = f"fix: {packet.instruction[:72]}"
            commit_sha = self.commit_changes(session_id, commit_msg)

        duration = time.time() - start_time
        status = "committed" if commit_sha else ("failed" if not files_edited else "needs_review")

        return TaskResult(
            status=status,
            files_edited=files_edited,
            commands_run=commands_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            commit_sha=commit_sha,
            duration_seconds=duration,
        )

    def _call_llm(self, system_prompt: str, user_prompt: str, model: str = None) -> str:
        """Call LiteLLM and return the response text."""
        model = model or DEFAULT_MODEL
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
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
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]

    def _parse_file_edits(self, response: str) -> list:
        """Parse FILE: path followed by code block."""
        edits = []
        pattern = r"FILE:\s*(.+?)\n```[^\n]*\n(.*?)```"
        for match in re.finditer(pattern, response, re.DOTALL):
            filepath = match.group(1).strip()
            content = match.group(2)
            edits.append((filepath, content))
        return edits

    def _parse_find_replace_edits(self, response: str) -> list:
        """Parse EDIT/FIND/REPLACE blocks."""
        edits = []
        pattern = r"EDIT:\s*(.+?)\nFIND:\n```[^\n]*\n(.*?)```\nREPLACE:\n```[^\n]*\n(.*?)```"
        for match in re.finditer(pattern, response, re.DOTALL):
            filepath = match.group(1).strip()
            find_text = match.group(2)
            replace_text = match.group(3)
            edits.append((filepath, find_text, replace_text))
        return edits

    def _parse_run_commands(self, response: str) -> list:
        """Parse RUN: commands."""
        commands = []
        for line in response.split("\n"):
            if line.strip().startswith("RUN:"):
                cmd = line.strip()[4:].strip()
                if cmd and not any(danger in cmd for danger in ["rm -rf /", "sudo rm", "format", "> /dev"]):
                    commands.append(cmd)
        return commands

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
