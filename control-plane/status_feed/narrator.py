"""Translate platform timeline events into user-facing status messages.

Executors write raw operational events to:

    /opt/workstation/sessions/<session_id>/events/events.jsonl

This module derives a separate natural-language stream for the session chat:

    /opt/workstation/sessions/<session_id>/chat/status.jsonl

The chat stream is intentionally concise. Raw events remain the source of truth
for debugging; status messages are for keeping the user oriented in real time.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path("/opt/workstation/sessions")

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|credential)", re.I)
SECRET_VALUE_RE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_/-]{32,})")
EDIT_TOOLS = {"write_file", "apply_patch", "FileEditorTool", "str_replace_editor", "edit_file"}
REASON_KEYS = ("reason", "rationale", "why", "explanation", "intent", "purpose")


class StatusNarrator:
    """Create and persist natural-language chat updates from timeline events."""

    def emit_for_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        message = self.describe_event(session_id, event)
        if not message:
            return None

        update = {
            "type": "status_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "source_event_type": event.get("type", "unknown"),
            **message,
        }
        self._append_status(session_id, update)
        return update

    def describe_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get("type")

        if event_type == "task_start":
            executor = event.get("executor", "executor")
            branch = event.get("branch")
            instruction = self._clip(event.get("instruction", "the task"), 140)
            text = f"I started the task with {executor}."
            detail = f"Task: {instruction}"
            if branch:
                detail += f" Branch: {branch}."
            return self._msg("started", text, detail=detail, severity="info", reason_source="task")

        if event_type == "queued":
            executor = event.get("executor", "executor")
            return self._msg("queued", f"I queued this task for {executor}.", severity="info")

        if event_type == "think":
            thought = self._clip(event.get("thought", ""), 240)
            if not thought:
                return self._msg("thinking", "I am planning the next step.", severity="info")
            return self._msg(
                "thinking",
                "I am planning the next step.",
                detail=thought,
                severity="info",
                reason_source="agent_thought",
            )

        if event_type == "tool_call":
            return self._describe_tool_call(session_id, event)

        if event_type == "stuck_detected":
            tool = event.get("tool", "a tool")
            return self._msg(
                "blocked",
                f"I detected repeated use of {tool} and am changing approach.",
                severity="warning",
            )

        if event_type == "llm_error":
            return self._msg(
                "error",
                "The model call failed while working on the task.",
                detail=self._clip(event.get("error", ""), 240),
                severity="error",
            )

        if event_type == "agent_message":
            text = self._clip(event.get("text", ""), 300)
            if not text:
                return None
            return self._msg("message", "The agent sent an update.", detail=text, severity="info")

        if event_type == "openhands_conversation_start":
            cid = self._clip(event.get("conversation_id", ""), 16)
            return self._msg(
                "started",
                "I started an OpenHands conversation for this session.",
                detail=f"Conversation: {cid}",
                severity="info",
            )

        if event_type == "openhands_status":
            status = str(event.get("status", "UNKNOWN")).upper()
            return self._describe_openhands_status(status)

        if event_type == "openhands_event":
            return self._describe_openhands_event(session_id, event)

        if event_type == "openhands_timeout":
            return self._msg(
                "blocked",
                "OpenHands did not finish before the run timeout.",
                detail=f"Timeout: {event.get('timeout_seconds', 'unknown')} seconds.",
                severity="warning",
            )

        if event_type == "openhands_error":
            return self._msg(
                "error",
                "OpenHands reported an execution error.",
                detail=self._clip(event.get("error", ""), 300),
                severity="error",
            )

        if event_type == "openhands_final_response_error":
            return self._msg(
                "warning",
                "I could not fetch the final OpenHands response, but the task state is still recorded.",
                detail=self._clip(event.get("error", ""), 240),
                severity="warning",
            )

        if event_type == "task_complete":
            return self._describe_task_complete(event)

        return None

    def _describe_tool_call(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        tool = str(event.get("tool", "tool"))
        success = bool(event.get("success", False))
        args = event.get("args") if isinstance(event.get("args"), dict) else {}

        if tool in {"write_file", "apply_patch"}:
            return self._describe_file_edit(session_id, tool, args, success)

        label_map = {
            "read_file": "I am reading a file.",
            "list_files": "I am listing files in the worktree.",
            "grep": "I am searching the codebase.",
            "run_command": "I am running a command.",
            "git_status": "I am checking git status.",
            "git_diff": "I am inspecting the diff.",
            "git_commit": "I am creating a commit.",
            "run_validation": "I am running validation.",
            "get_latest_context": "I am refreshing session context.",
            "task_complete": "I am marking the task complete.",
        }
        text = label_map.get(tool, f"I am using {tool}.")

        detail_parts = []
        for key in ("path", "command", "message", "pattern", "reason", "rationale", "why"):
            if key in args:
                detail_parts.append(f"{key}: {self._clip(args[key], 220)}")

        if not success and tool != "think":
            text = f"{text} The last attempt did not succeed."
            severity = "warning"
        else:
            severity = "info"

        return self._msg("working", text, detail="; ".join(detail_parts) or None, severity=severity)

    def _describe_file_edit(
        self,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        success: bool,
    ) -> dict[str, Any]:
        path = self._clip(args.get("path", "the target file"), 180)
        reason = self._extract_reason(args)
        reason_source = "explicit_tool_reason" if reason else None

        if not reason:
            reason, reason_source = self._find_recent_reason(session_id)

        operation = "writing" if tool == "write_file" else "patching"

        if reason:
            prefix = "because" if reason_source == "explicit_tool_reason" else "based on"
            text = f"I am {operation} {path} {prefix} {self._clip(reason, 240)}."
            detail = None
        else:
            text = f"I am {operation} {path}."
            detail = "I could not find an explicit or recent rationale for this edit."

        if not success:
            text += " The edit attempt did not succeed."
            severity = "warning"
        else:
            severity = "info"

        return self._msg("editing", text, detail=detail, severity=severity, reason_source=reason_source)

    def _describe_openhands_status(self, status: str) -> dict[str, Any] | None:
        if status == "UNKNOWN":
            return None
        mapping = {
            "IDLE": ("waiting", "OpenHands is idle and ready for the next instruction.", "info"),
            "RUNNING": ("working", "OpenHands is actively working on the task.", "info"),
            "FINISHED": ("finished", "OpenHands finished its run. I am checking the result.", "success"),
            "PAUSED": ("paused", "OpenHands is paused.", "warning"),
            "ERROR": ("error", "OpenHands ended with an error.", "error"),
            "STUCK": ("blocked", "OpenHands appears to be stuck.", "warning"),
            "TIMEOUT": ("blocked", "OpenHands reached the run timeout.", "warning"),
        }
        phase, text, severity = mapping.get(status, ("working", f"OpenHands status is {status}.", "info"))
        return self._msg(phase, text, severity=severity)

    def _describe_openhands_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
        raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
        kind = str(summary.get("kind") or "OpenHands event")
        source = summary.get("source")

        if "MessageEvent" in kind:
            role = summary.get("role") or source or "agent"
            text = summary.get("text")
            if text:
                return self._msg(
                    "message",
                    f"OpenHands sent a {role} message.",
                    detail=self._clip(text, 300),
                    severity="info",
                    reason_source="agent_message",
                )
            return self._msg("message", f"OpenHands sent a {role} message.", severity="info")

        if "ActionEvent" in kind:
            tool = str(summary.get("tool_name") or summary.get("action") or self._recursive_find(raw, ("tool_name", "name", "tool")) or "a tool")
            path = self._recursive_find(raw, ("path", "file", "file_path", "target_file"))
            reason = self._extract_reason(raw)
            reason_source = "explicit_openhands_event" if reason else None
            if not reason:
                reason, reason_source = self._find_recent_reason(session_id)

            if self._looks_like_edit_tool(tool) or path:
                if path and reason:
                    prefix = "because" if reason_source == "explicit_openhands_event" else "based on"
                    return self._msg(
                        "editing",
                        f"OpenHands is editing {self._clip(path, 180)} {prefix} {self._clip(reason, 240)}.",
                        severity="info",
                        reason_source=reason_source,
                    )
                if path:
                    return self._msg(
                        "editing",
                        f"OpenHands is editing {self._clip(path, 180)}.",
                        detail="I could not find an explicit or recent rationale for this edit.",
                        severity="info",
                    )
                if reason:
                    return self._msg(
                        "editing",
                        f"OpenHands is making an edit based on {self._clip(reason, 240)}.",
                        severity="info",
                        reason_source=reason_source,
                    )

            return self._msg("working", f"OpenHands is using {tool}.", severity="info")

        if "ObservationEvent" in kind:
            observation = summary.get("observation")
            return self._msg(
                "observing",
                "OpenHands received a tool result.",
                detail=self._clip(observation, 240) if observation else None,
                severity="info",
            )

        if "Error" in kind or summary.get("error") or summary.get("detail"):
            return self._msg(
                "error",
                "OpenHands reported an error event.",
                detail=self._clip(summary.get("error") or summary.get("detail") or "", 300),
                severity="error",
            )

        return None

    def _describe_task_complete(self, event: dict[str, Any]) -> dict[str, Any]:
        status = str(event.get("status", "completed"))
        commit = event.get("commit")
        changed = event.get("changed")
        validation = event.get("validation")

        if status == "committed" and commit:
            return self._msg(
                "finished",
                "I finished the task and committed the changes.",
                detail=f"Commit: {commit}",
                severity="success",
            )

        if status == "needs_review":
            detail = "Changes were made and need review."
            if validation:
                detail += f" Validation: {self._clip(validation, 220)}"
            return self._msg("review", "I made changes, but they need review.", detail=detail, severity="warning")

        if status == "failed":
            return self._msg(
                "error",
                "I could not complete the task successfully.",
                detail=self._clip(event.get("error", ""), 240),
                severity="error",
            )

        if changed is False:
            return self._msg("finished", "I finished without making code changes.", severity="success")

        return self._msg("finished", f"The task finished with status {status}.", severity="success")

    def _append_status(self, session_id: str, update: dict[str, Any]) -> None:
        chat_dir = SESSIONS_DIR / session_id / "chat"
        chat_dir.mkdir(parents=True, exist_ok=True)
        status_file = chat_dir / "status.jsonl"
        with open(status_file, "a") as f:
            f.write(json.dumps(update, default=str) + "\n")

    def _msg(
        self,
        phase: str,
        text: str,
        detail: str | None = None,
        severity: str = "info",
        reason_source: str | None = None,
    ) -> dict[str, Any]:
        message = {
            "phase": phase,
            "severity": severity,
            "text": self._redact(text),
            "detail": self._redact(detail) if detail else None,
        }
        if reason_source:
            message["reason_source"] = reason_source
        return message

    def _extract_reason(self, value: Any) -> str | None:
        found = self._recursive_find(value, REASON_KEYS)
        if found is None:
            return None
        text = str(found).strip()
        return text or None

    def _find_recent_reason(self, session_id: str) -> tuple[str | None, str | None]:
        events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
        if not events_file.exists():
            return None, None

        try:
            lines = events_file.read_text().splitlines()[-80:]
        except OSError:
            return None, None

        task_instruction = None
        for line in reversed(lines):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type == "think" and event.get("thought"):
                return str(event["thought"]), "recent_agent_thought"
            if event_type == "agent_message" and event.get("text"):
                return str(event["text"]), "recent_agent_message"
            if event_type == "openhands_event":
                summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
                text = summary.get("text")
                if text:
                    return str(text), "recent_openhands_message"
            if event_type == "task_start" and event.get("instruction") and task_instruction is None:
                task_instruction = str(event["instruction"])

        if task_instruction:
            return task_instruction, "task_instruction"
        return None, None

    def _recursive_find(self, value: Any, keys: tuple[str, ...]) -> Any | None:
        if isinstance(value, dict):
            for key in keys:
                if key in value and value[key]:
                    return value[key]
            for nested in value.values():
                result = self._recursive_find(nested, keys)
                if result is not None:
                    return result
        elif isinstance(value, list):
            for item in value:
                result = self._recursive_find(item, keys)
                if result is not None:
                    return result
        return None

    @staticmethod
    def _looks_like_edit_tool(tool: str) -> bool:
        lowered = tool.lower()
        return tool in EDIT_TOOLS or "edit" in lowered or "patch" in lowered or "write" in lowered

    @staticmethod
    def _clip(value: Any, limit: int) -> str:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        text = text.replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _redact(value: str) -> str:
        if not value:
            return value
        redacted = SECRET_VALUE_RE.sub("***redacted***", value)
        parts = []
        for token in redacted.split():
            if SECRET_KEY_RE.search(token):
                parts.append("***redacted***")
            else:
                parts.append(token)
        return " ".join(parts)


_default_narrator = StatusNarrator()


def emit_status_for_event(session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    """Translate and persist one raw timeline event as a chat status update."""

    return _default_narrator.emit_for_event(session_id, event)
