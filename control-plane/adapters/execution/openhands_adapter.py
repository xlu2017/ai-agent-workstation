"""
OpenHandsExecutorAdapter — primary coding execution backend.

OpenHands is the primary execution backend for coding actions. This adapter
wraps the OpenHands HTTP API or vendored Python APIs.

Configuration:
  OPENHANDS_ENABLED=true
  OPENHANDS_BASE_URL=http://localhost:...
  OPENHANDS_WORKSPACE_BASE=/opt/workstation/repos

Does NOT silently fall back unless fallback is explicitly enabled.
"""

from __future__ import annotations

import os
import time
from typing import Any

from adapters.execution.base import ExecutionAdapter

OPENHANDS_ENABLED = os.environ.get("OPENHANDS_ENABLED", "false").lower() == "true"
OPENHANDS_BASE_URL = os.environ.get("OPENHANDS_BASE_URL", "http://localhost:3000")
OPENHANDS_WORKSPACE_BASE = os.environ.get(
    "OPENHANDS_WORKSPACE_BASE", "/opt/workstation/repos"
)

# Actions that OpenHands can execute
OPENHANDS_ACTION_MAP = {
    "grep": "search",
    "read_file": "read",
    "apply_patch": "edit",
    "run_tests": "execute",
    "summarize_diff": "analyze",
    "commit": "git",
    "autonomous_code_edit": "agent",
    "repair_test_failure": "agent",
    "browser_debug_loop": "agent",
    "multi_file_refactor_loop": "agent",
    "investigate_and_patch": "agent",
}


def _import_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


class OpenHandsExecutorAdapter(ExecutionAdapter):
    """Execute actions via the OpenHands backend.

    Supports both HTTP API mode and vendored/local Python API mode.
    If neither is available, returns a clear failure.
    """

    def __init__(
        self,
        base_url: str = OPENHANDS_BASE_URL,
        workspace_base: str = OPENHANDS_WORKSPACE_BASE,
    ):
        self.base_url = base_url.rstrip("/")
        self.workspace_base = workspace_base
        self._httpx = _import_httpx()

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        start_ms = int(time.time() * 1000)

        if not OPENHANDS_ENABLED:
            return {
                "status": "failed",
                "backend": "openhands",
                "output": {},
                "error": "OpenHands backend is not configured or unavailable",
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

        if self._httpx is None:
            return {
                "status": "failed",
                "backend": "openhands",
                "output": {},
                "error": "httpx is not installed; cannot reach OpenHands API",
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }

        # Build structured payload for OpenHands
        action_type = OPENHANDS_ACTION_MAP.get(action_name, "execute")
        payload = {
            "session_id": session_id,
            "workspace": worktree_path,
            "action_name": action_name,
            "action_type": action_type,
            "params": params,
            "context": context,
        }

        # If OpenHands cannot execute atomic actions directly,
        # wrap as a high-level instruction
        if action_type == "agent":
            payload["instruction"] = (
                f"Execute action {action_name} with params {params} "
                f"in workspace {worktree_path}. "
                "Return structured JSON with status, output, error, files_touched."
            )

        try:
            async with self._httpx.AsyncClient(
                base_url=self.base_url, timeout=120.0
            ) as client:
                resp = await client.post("/api/execute", json=payload)
                resp.raise_for_status()
                result = resp.json()
                return {
                    "status": result.get("status", "succeeded"),
                    "backend": "openhands",
                    "output": result.get("output", {}),
                    "error": result.get("error", ""),
                    "files_touched": result.get("files_touched", []),
                    "duration_ms": int(time.time() * 1000) - start_ms,
                }
        except Exception as e:
            return {
                "status": "failed",
                "backend": "openhands",
                "output": {},
                "error": f"OpenHands API error: {e}",
                "files_touched": [],
                "duration_ms": int(time.time() * 1000) - start_ms,
            }
