"""
OpenHandsExecutorAdapter — delegate platform tasks to an OpenHands agent-server.

This adapter preserves the platform's ExecutorAdapter contract while making
OpenHands the canonical execution runtime. The platform owns session/worktree
metadata, timeline projection, validation, and final reporting. OpenHands owns
the agent loop, tool system, conversation state, hooks, skills/plugins, MCP, and
runtime behavior.

Default target API is the OpenHands SDK agent-server shape:

    POST /conversations
    POST /conversations/{conversation_id}/run
    GET  /conversations/{conversation_id}
    GET  /conversations/{conversation_id}/events/search

If your deployment exposes these routes under /api, set OPENHANDS_API_PREFIX=/api
or OPENHANDS_API_PREFIXES='["", "/api"]'.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.base import ExecutorAdapter, TaskPacket, TaskResult, SESSIONS_DIR


OPENHANDS_URL = os.environ.get("OPENHANDS_URL", "http://localhost:3000").rstrip("/")
OPENHANDS_API_KEY = os.environ.get("OPENHANDS_API_KEY", "")
OPENHANDS_REQUEST_TIMEOUT = int(os.environ.get("OPENHANDS_REQUEST_TIMEOUT", "30"))
OPENHANDS_RUN_TIMEOUT_SECONDS = int(os.environ.get("OPENHANDS_RUN_TIMEOUT_SECONDS", "1800"))
OPENHANDS_POLL_INTERVAL_SECONDS = float(os.environ.get("OPENHANDS_POLL_INTERVAL_SECONDS", "2"))
OPENHANDS_MAX_ITERATIONS = int(os.environ.get("OPENHANDS_MAX_ITERATIONS", "500"))

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")

PROTECTED_BRANCHES = {"main", "master", "develop", "production"}
TERMINAL_STATUSES = {"FINISHED", "ERROR", "STUCK", "PAUSED"}


class OpenHandsHTTPError(RuntimeError):
    """Raised when the OpenHands HTTP API returns an error."""

    def __init__(self, method: str, url: str, status: int | None, body: str):
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"{method} {url} failed ({status}): {body[:500]}")


class OpenHandsClient:
    """Small urllib-based client for the OpenHands conversation API."""

    def __init__(
        self,
        base_url: str = OPENHANDS_URL,
        api_key: str = OPENHANDS_API_KEY,
        request_timeout: int = OPENHANDS_REQUEST_TIMEOUT,
        api_prefix: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.request_timeout = request_timeout
        self.api_prefix = self._normalize_prefix(api_prefix or self._default_prefixes()[0])
        self._candidate_prefixes = self._default_prefixes()

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        prefix = (prefix or "").strip()
        if not prefix:
            return ""
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        return prefix.rstrip("/")

    @staticmethod
    def _default_prefixes() -> list[str]:
        configured = os.environ.get("OPENHANDS_API_PREFIXES")
        if configured:
            try:
                raw = json.loads(configured)
                if isinstance(raw, list):
                    return [OpenHandsClient._normalize_prefix(str(p)) for p in raw]
            except json.JSONDecodeError:
                return [
                    OpenHandsClient._normalize_prefix(p)
                    for p in configured.split(",")
                    if p.strip()
                ]

        single = os.environ.get("OPENHANDS_API_PREFIX")
        if single is not None:
            return [OpenHandsClient._normalize_prefix(single)]

        return ["", "/api"]

    def _url(self, path: str, query: dict[str, Any] | None = None, prefix: str | None = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        full = f"{self.base_url}{self._normalize_prefix(prefix if prefix is not None else self.api_prefix)}{path}"
        if query:
            encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
            if encoded:
                full = f"{full}?{encoded}"
        return full

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        prefix: str | None = None,
    ) -> dict[str, Any] | list[Any] | str | int | None:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        url = self._url(path, query=query, prefix=prefix)
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise OpenHandsHTTPError(method, url, e.code, body) from e
        except urllib.error.URLError as e:
            raise OpenHandsHTTPError(method, url, None, str(e)) from e

    def _request_first_success(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | str | int | None:
        last_error: OpenHandsHTTPError | None = None
        for prefix in self._candidate_prefixes:
            try:
                result = self._request(method, path, payload=payload, query=query, prefix=prefix)
                self.api_prefix = self._normalize_prefix(prefix)
                return result
            except OpenHandsHTTPError as e:
                last_error = e
                if e.status not in (404, 405):
                    raise
        assert last_error is not None
        raise last_error

    def start_conversation(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request_first_success("POST", "/conversations", payload=payload)
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected OpenHands start response: {result!r}")
        return result

    def run_conversation(self, conversation_id: str) -> None:
        result = self._request("POST", f"/conversations/{conversation_id}/run")
        if result is not None and not isinstance(result, dict):
            raise RuntimeError(f"Unexpected OpenHands run response: {result!r}")

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        result = self._request("GET", f"/conversations/{conversation_id}")
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected OpenHands conversation response: {result!r}")
        return result

    def search_events(
        self,
        conversation_id: str,
        page_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"/conversations/{conversation_id}/events/search",
            query={"page_id": page_id, "limit": limit, "sort_order": "TIMESTAMP"},
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected OpenHands events response: {result!r}")
        return result

    def get_agent_final_response(self, conversation_id: str) -> str:
        result = self._request("GET", f"/conversations/{conversation_id}/agent_final_response")
        if isinstance(result, dict):
            value = result.get("response", "")
            return value if isinstance(value, str) else str(value)
        return "" if result is None else str(result)


class OpenHandsExecutorAdapter(ExecutorAdapter):
    """
    ExecutorAdapter implementation that delegates agent execution to OpenHands.

    The adapter intentionally does not reimplement OpenHands behavior. It only:
    - creates/runs an OpenHands conversation for the platform task packet
    - mirrors OpenHands conversation/events into the platform timeline
    - gathers git diff/validation/commit state from the platform worktree
    - returns a TaskResult to the control plane
    """

    def __init__(self, client: OpenHandsClient | None = None):
        self.client = client or OpenHandsClient()

    def is_available(self) -> bool:
        """Check if OpenHands API is reachable."""
        try:
            url = f"{self.client.base_url}/health"
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            # Try conversation list as health check fallback
            try:
                self.client._request_first_success("GET", "/conversations")
                return True
            except Exception:
                return False

    def run_task(self, session_id: str, packet: TaskPacket) -> TaskResult:
        start_time = time.time()
        session_dir = SESSIONS_DIR / session_id
        events_dir = session_dir / "events"
        session_dir.mkdir(parents=True, exist_ok=True)
        events_dir.mkdir(parents=True, exist_ok=True)

        worktree = packet.worktree_path
        if not worktree or not Path(worktree).exists():
            return TaskResult(status="failed", error="No worktree found", duration_seconds=0)

        branch = self._get_current_branch(worktree) or packet.branch
        if branch in PROTECTED_BRANCHES:
            return TaskResult(
                status="failed",
                error=f"Cannot execute on protected branch: {branch}",
                duration_seconds=0,
            )

        self._ensure_session_meta(session_id, worktree, branch)
        packet.save()

        self._record_timeline_event(
            session_id,
            "task_start",
            {
                "task_id": packet.task_id,
                "instruction": packet.instruction[:500],
                "executor": "openhands",
                "worktree": worktree,
                "branch": branch,
            },
        )

        conversation_id: str | None = None
        seen_event_ids: set[str] = set()
        last_status = "UNKNOWN"
        final_response = ""

        try:
            payload = self._build_start_payload(session_id, packet, worktree, branch)
            info = self.client.start_conversation(payload)
            conversation_id = self._extract_conversation_id(info)

            self._write_openhands_meta(session_id, conversation_id, payload, info)
            self._record_timeline_event(
                session_id,
                "openhands_conversation_start",
                {
                    "conversation_id": conversation_id,
                    "api_prefix": self.client.api_prefix,
                    "openhands_url": self.client.base_url,
                },
            )

            try:
                self.client.run_conversation(conversation_id)
            except OpenHandsHTTPError as e:
                if e.status != 409:
                    raise
                self._record_timeline_event(
                    session_id,
                    "openhands_already_running",
                    {"conversation_id": conversation_id},
                )

            deadline = time.time() + OPENHANDS_RUN_TIMEOUT_SECONDS
            while time.time() < deadline:
                info = self.client.get_conversation(conversation_id)
                last_status = self._extract_status(info)
                self._mirror_openhands_events(session_id, conversation_id, seen_event_ids)

                self._record_timeline_event(
                    session_id,
                    "openhands_status",
                    {
                        "conversation_id": conversation_id,
                        "status": last_status,
                    },
                )

                if last_status in TERMINAL_STATUSES:
                    break
                time.sleep(OPENHANDS_POLL_INTERVAL_SECONDS)
            else:
                last_status = "TIMEOUT"
                self._record_timeline_event(
                    session_id,
                    "openhands_timeout",
                    {
                        "conversation_id": conversation_id,
                        "timeout_seconds": OPENHANDS_RUN_TIMEOUT_SECONDS,
                    },
                )

            self._mirror_openhands_events(session_id, conversation_id, seen_event_ids)
            if last_status == "FINISHED":
                try:
                    final_response = self.client.get_agent_final_response(conversation_id)
                except Exception as e:
                    self._record_timeline_event(
                        session_id,
                        "openhands_final_response_error",
                        {"error": str(e)[:500]},
                    )

        except Exception as e:
            self._record_timeline_event(
                session_id,
                "openhands_error",
                {
                    "conversation_id": conversation_id,
                    "error": str(e)[:2000],
                },
            )
            return TaskResult(
                status="failed",
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        diff = self._git_diff(worktree)
        changed = bool(diff.strip())

        validation_result = None
        tests_passed = 0
        tests_failed = 0
        if changed:
            validation_result = self.run_validation(session_id)
            test_result = validation_result.get("results", {}).get("test")
            if test_result is not None:
                tests_passed = 1 if test_result.get("passed") else 0
                tests_failed = 0 if test_result.get("passed") else 1

        commit_sha = None
        if changed and last_status == "FINISHED":
            commit_sha = self.commit_changes(session_id, f"fix: {packet.instruction[:72]}")

        duration = time.time() - start_time
        if last_status in {"ERROR", "STUCK", "TIMEOUT"}:
            status = "needs_review" if changed else "failed"
        elif commit_sha:
            status = "committed"
        elif changed:
            status = "needs_review"
        else:
            status = "completed"

        self._record_timeline_event(
            session_id,
            "task_complete",
            {
                "task_id": packet.task_id,
                "executor": "openhands",
                "conversation_id": conversation_id,
                "openhands_status": last_status,
                "status": status,
                "changed": changed,
                "commit": commit_sha,
                "validation": validation_result,
                "duration": duration,
            },
        )

        return TaskResult(
            status=status,
            files_edited=self._changed_files(worktree),
            commands_run=[],
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            commit_sha=commit_sha,
            error=None if status != "failed" else f"OpenHands ended with status {last_status}",
            summary=final_response,
            duration_seconds=duration,
        )

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

    def _build_start_payload(
        self,
        session_id: str,
        packet: TaskPacket,
        worktree: str,
        branch: str,
    ) -> dict[str, Any]:
        template = os.environ.get("OPENHANDS_START_CONVERSATION_PAYLOAD_JSON")
        task_markdown = packet.to_markdown()

        if template:
            return self._render_payload_template(
                template,
                {
                    "session_id": session_id,
                    "task_id": packet.task_id,
                    "instruction": packet.instruction,
                    "task_markdown": task_markdown,
                    "worktree_path": worktree,
                    "branch": branch,
                    "model": packet.model or DEFAULT_MODEL,
                    "litellm_url": LITELLM_URL,
                    "litellm_key": LITELLM_KEY,
                },
            )

        return {
            "conversation_id": str(uuid.uuid4()),
            "workspace": {
                "kind": "LocalWorkspace",
                "working_dir": worktree,
            },
            "worktree": False,
            "initial_message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": task_markdown,
                    }
                ],
                "run": False,
            },
            "max_iterations": OPENHANDS_MAX_ITERATIONS,
            "stuck_detection": True,
            "tags": {
                "platform": "jubilantgoggles",
                "session": session_id[:256],
                "task": packet.task_id[:256],
                "branch": branch[:256],
            },
            "agent": self._build_agent_payload(packet),
        }

    def _build_agent_payload(self, packet: TaskPacket) -> dict[str, Any]:
        configured = os.environ.get("OPENHANDS_AGENT_PAYLOAD_JSON")
        if configured:
            return self._render_payload_template(
                configured,
                {
                    "model": packet.model or DEFAULT_MODEL,
                    "litellm_url": LITELLM_URL,
                    "litellm_key": LITELLM_KEY,
                },
            )

        tools = os.environ.get("OPENHANDS_TOOL_SPECS_JSON")
        if tools:
            try:
                tool_specs = json.loads(tools)
            except json.JSONDecodeError as e:
                raise ValueError("OPENHANDS_TOOL_SPECS_JSON must be valid JSON") from e
        else:
            tool_specs = [
                {"name": "TerminalTool", "params": {}},
                {"name": "FileEditorTool", "params": {}},
                {"name": "TaskTrackerTool", "params": {}},
            ]

        llm: dict[str, Any] = {
            "usage_id": "platform-default",
            "model": packet.model or DEFAULT_MODEL,
        }
        if LITELLM_URL:
            llm["base_url"] = LITELLM_URL
        if LITELLM_KEY:
            llm["api_key"] = LITELLM_KEY

        return {
            "kind": "Agent",
            "llm": llm,
            "tools": tool_specs,
            "include_default_tools": ["FinishTool", "ThinkTool"],
            "system_prompt_kwargs": {
                "cli_mode": True,
            },
        }

    @staticmethod
    def _render_payload_template(template: str, values: dict[str, str]) -> dict[str, Any]:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        try:
            payload = json.loads(rendered)
        except json.JSONDecodeError as e:
            raise ValueError("OpenHands payload template rendered invalid JSON") from e
        if not isinstance(payload, dict):
            raise ValueError("OpenHands payload template must render to a JSON object")
        return payload

    def _mirror_openhands_events(
        self,
        session_id: str,
        conversation_id: str,
        seen_event_ids: set[str],
    ) -> None:
        page_id: str | None = None
        pages = 0
        while pages < 10:
            page = self.client.search_events(conversation_id, page_id=page_id, limit=100)
            items = page.get("items", [])
            if not isinstance(items, list):
                return

            for event in items:
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("id") or event.get("event_id") or self._event_fingerprint(event))
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                self._record_timeline_event(
                    session_id,
                    "openhands_event",
                    {
                        "conversation_id": conversation_id,
                        "event_id": event_id,
                        "summary": self._summarize_event(event),
                        "raw": self._truncate_jsonable(event, 6000),
                    },
                )

            page_id = page.get("next_page_id")
            if not page_id:
                break
            pages += 1

    @staticmethod
    def _summarize_event(event: dict[str, Any]) -> dict[str, Any]:
        kind = event.get("kind") or event.get("type") or event.get("event_type") or event.get("class")
        summary: dict[str, Any] = {
            "kind": kind,
            "source": event.get("source"),
            "timestamp": event.get("timestamp"),
        }

        for key in ("tool_name", "action", "observation", "error", "code", "detail"):
            if key in event:
                summary[key] = str(event[key])[:500]

        message = event.get("llm_message")
        if isinstance(message, dict):
            summary["role"] = message.get("role")
            content = message.get("content")
            if isinstance(content, list):
                texts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and isinstance(c.get("text"), str)
                ]
                if texts:
                    summary["text"] = "\n".join(texts)[:1000]

        return summary

    @staticmethod
    def _truncate_jsonable(value: Any, max_chars: int) -> Any:
        text = json.dumps(value, default=str)
        if len(text) <= max_chars:
            return value
        return {"truncated": True, "preview": text[:max_chars]}

    @staticmethod
    def _event_fingerprint(event: dict[str, Any]) -> str:
        return str(hash(json.dumps(event, sort_keys=True, default=str)))

    @staticmethod
    def _extract_conversation_id(info: dict[str, Any]) -> str:
        value = info.get("id") or info.get("conversation_id")
        if not value:
            raise RuntimeError(f"OpenHands response did not include conversation id: {info}")
        return str(value)

    @staticmethod
    def _extract_status(info: dict[str, Any]) -> str:
        value = info.get("execution_status") or info.get("status") or "UNKNOWN"
        if isinstance(value, dict):
            value = value.get("value") or value.get("name") or str(value)
        return str(value).upper()

    @staticmethod
    def _get_current_branch(worktree: str) -> str:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    @staticmethod
    def _git_diff(worktree: str) -> str:
        try:
            staged = subprocess.run(
                ["git", "diff", "--staged"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            if staged.strip():
                return staged
            return subprocess.run(
                ["git", "diff"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except Exception:
            return ""

    @staticmethod
    def _changed_files(worktree: str) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            )
            files = []
            for line in result.stdout.splitlines():
                if len(line) > 3:
                    files.append(line[3:].strip())
            return files
        except Exception:
            return []

    @staticmethod
    def _ensure_session_meta(session_id: str, worktree: str, branch: str) -> None:
        session_dir = SESSIONS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta_path = session_dir / "session.json"
        if meta_path.exists():
            return
        meta_path.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "worktree_path": worktree,
                    "branch": branch,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
        )

    @staticmethod
    def _write_openhands_meta(
        session_id: str,
        conversation_id: str,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        session_dir = SESSIONS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        sanitized_payload = json.loads(json.dumps(payload, default=str))
        agent = sanitized_payload.get("agent")
        if isinstance(agent, dict):
            llm = agent.get("llm")
            if isinstance(llm, dict) and "api_key" in llm:
                llm["api_key"] = "***redacted***"

        (session_dir / "openhands.json").write_text(
            json.dumps(
                {
                    "conversation_id": conversation_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "request": sanitized_payload,
                    "response": response,
                },
                indent=2,
            )
        )
