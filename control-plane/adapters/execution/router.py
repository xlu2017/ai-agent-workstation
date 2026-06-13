"""
ExecutionRouter — capability-aware routing to agentic, deterministic, or app automation execution.

Routing policy:

  DeterministicExecutor:
    grep, search_code, read_file, list_files, git_status, git_diff,
    inspect_diff, summarize_diff, apply_patch (with explicit patch/content),
    run_tests (explicit command, no repair loop), run_lint, run_typecheck,
    write_file, commit

  AgenticExecutor:
    autonomous_code_edit, investigate_and_patch, repair_test_failure,
    apply_patch (with intent), run_tests (when repair/diagnosis requested),
    run_command (when interpretation needed)

  App automation executor:
    provider-neutral app actions such as email.create, email.search,
    message.send, issue.create, browser_task.perform. Provider-specific app
    choices are params and are dispatched directly to vendor runtimes/adapters.

  Platform-native (not routed through coding executors):
    request_approval, wait_for_approval, request_credential, wait_for_secret,
    record_skipped_validation, restart_service, update_latest_from_github,
    start_service, stop_service, create_pr, check_pr_status, check_ci_status,
    merge_pr, open_remote_desktop, browser actions

Configuration:
  EXECUTOR_BACKEND=agentic | deterministic
  AGENTIC_EXECUTOR_ENABLED=true
  ALLOW_DETERMINISTIC_EXECUTOR=true
"""

from __future__ import annotations

import os
from typing import Any

from adapters.execution.base import ExecutionAdapter
from api.app_automation.executor import execute_app_action
from api.app_automation.models import AppAutomationExecuteRequest
from api.app_automation.provider_neutral import is_provider_neutral_app_action, resolve_provider_neutral_app_action
from execution.deterministic_executor import DeterministicExecutor
from execution.agentic_executor import AgenticExecutor
from execution.results import ExecutionResult


# Actions that deterministic executor handles directly
DETERMINISTIC_ACTIONS = {
    "grep", "search_code", "read_file", "list_files",
    "git_status", "git_diff", "inspect_diff", "summarize_diff",
    "run_lint", "run_typecheck", "write_file",
}

# Actions that always go to the agentic executor
AGENTIC_ONLY_ACTIONS = {
    "autonomous_code_edit",
    "investigate_and_patch",
    "repair_test_failure",
}

# Actions that need context-aware routing
CONTEXT_ROUTED_ACTIONS = {
    "apply_patch",  # intent -> agentic, exact patch/content -> deterministic
    "run_tests",    # repair loop -> agentic, explicit command -> deterministic
    "run_command",  # simple -> deterministic, interpretation -> agentic
    "commit",       # always deterministic when explicitly assigned
}


class ExecutionRouter:
    """Capability-aware router selecting agentic, deterministic, or app automation execution."""

    def __init__(
        self,
        executor_backend: str | None = None,
        agentic_enabled: bool | None = None,
        allow_deterministic: bool | None = None,
        # Legacy aliases (map to new names)
        openhands_enabled: bool | None = None,
        allow_fallback: bool | None = None,
    ):
        raw_backend = executor_backend or os.environ.get("EXECUTOR_BACKEND", "")
        # Map legacy backend names
        _legacy_map = {"openhands": "agentic", "fallback": "deterministic"}
        self._backend = _legacy_map.get(raw_backend, raw_backend)

        # Resolve agentic_enabled (legacy: openhands_enabled)
        resolved_agentic = agentic_enabled if agentic_enabled is not None else openhands_enabled
        self._agentic_enabled = (
            resolved_agentic
            if resolved_agentic is not None
            else os.environ.get("AGENTIC_EXECUTOR_ENABLED", "false").lower() == "true"
        )

        # Resolve allow_deterministic (legacy: allow_fallback)
        resolved_deterministic = allow_deterministic if allow_deterministic is not None else allow_fallback
        self._allow_deterministic = (
            resolved_deterministic
            if resolved_deterministic is not None
            else os.environ.get("ALLOW_DETERMINISTIC_EXECUTOR", "false").lower() == "true"
        )

        self._agentic: AgenticExecutor | None = None
        self._deterministic: DeterministicExecutor | None = None

    def _get_agentic(self) -> AgenticExecutor:
        if self._agentic is None:
            self._agentic = AgenticExecutor()
        return self._agentic

    def _get_deterministic(self) -> DeterministicExecutor:
        if self._deterministic is None:
            self._deterministic = DeterministicExecutor()
        return self._deterministic

    def _route_action(
        self, action_name: str, params: dict[str, Any],
    ) -> tuple[ExecutionAdapter, str, bool, str]:
        """Determine which coding executor handles the action.

        Returns: (adapter, backend_name, is_fallback, fallback_reason)
        """
        # Forced backend override
        if self._backend == "agentic":
            return self._get_agentic(), "agentic", False, ""
        if self._backend == "deterministic":
            return self._get_deterministic(), "deterministic", False, ""

        # Agentic-only actions
        if action_name in AGENTIC_ONLY_ACTIONS:
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""
            if self._allow_deterministic:
                return (
                    self._get_deterministic(), "deterministic", True,
                    f"Agentic executor not enabled; falling back for {action_name}",
                )
            raise RuntimeError(
                f"Action {action_name} requires agentic executor but "
                "AGENTIC_EXECUTOR_ENABLED is not true and "
                "ALLOW_DETERMINISTIC_EXECUTOR is not true."
            )

        # Deterministic-preferred actions
        if action_name in DETERMINISTIC_ACTIONS:
            if self._allow_deterministic:
                return self._get_deterministic(), "deterministic", False, ""
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""
            raise RuntimeError(
                f"No executor configured for {action_name}. "
                "Set AGENTIC_EXECUTOR_ENABLED=true or ALLOW_DETERMINISTIC_EXECUTOR=true."
            )

        # Context-routed actions
        if action_name == "apply_patch":
            has_intent = bool(params.get("intent"))
            has_exact = bool(params.get("patch") or params.get("content"))
            if has_intent and not has_exact and self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""
            if self._allow_deterministic:
                return self._get_deterministic(), "deterministic", False, ""
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""

        if action_name == "run_tests":
            needs_repair = bool(params.get("repair") or params.get("diagnose"))
            if needs_repair and self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""
            if self._allow_deterministic:
                return self._get_deterministic(), "deterministic", False, ""
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""

        if action_name == "commit":
            if self._allow_deterministic:
                return self._get_deterministic(), "deterministic", False, ""
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""

        if action_name == "run_command":
            if self._agentic_enabled:
                return self._get_agentic(), "agentic", False, ""
            if self._allow_deterministic:
                return self._get_deterministic(), "deterministic", False, ""

        # Default resolution
        if self._agentic_enabled:
            return self._get_agentic(), "agentic", False, ""
        if self._allow_deterministic:
            return self._get_deterministic(), "deterministic", False, ""

        raise RuntimeError(
            "No execution backend configured. Set EXECUTOR_BACKEND=agentic "
            "or EXECUTOR_BACKEND=deterministic, or enable AGENTIC_EXECUTOR_ENABLED=true "
            "or ALLOW_DETERMINISTIC_EXECUTOR=true."
        )

    async def execute_action(
        self,
        session_id: str,
        worktree_path: str,
        action_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> ExecutionResult:
        if is_provider_neutral_app_action(action_name):
            return self._execute_app_automation_action(session_id, action_name, params)

        adapter, backend_name, is_fallback, fallback_reason = self._route_action(
            action_name, params,
        )
        result = await adapter.execute_action(
            session_id, worktree_path, action_name, params, context,
        )
        if is_fallback:
            result.fallback_used = True
            result.fallback_reason = fallback_reason
        return result

    def _execute_app_automation_action(self, session_id: str, action_name: str, params: dict[str, Any]) -> ExecutionResult:
        try:
            resolved = resolve_provider_neutral_app_action(action_name, params)
            request = AppAutomationExecuteRequest(
                app_id=resolved.app_id,
                action_id=resolved.action_id,
                params=resolved.params,
                session_id=session_id,
                dry_run=bool(resolved.params.get("dry_run", False)),
                approval_granted=bool(resolved.params.get("approval_granted") or resolved.params.get("platform_approval_granted")),
            )
            result = execute_app_action(request)
        except Exception as exc:  # pragma: no cover - defensive platform boundary
            return ExecutionResult(
                status="failed",
                backend="app_automation",
                summary=f"App automation dispatch failed for {action_name}.",
                error=str(exc),
                output={"action_name": action_name},
            )

        status = "succeeded" if result.ok and result.status not in {"needs_approval", "invalid_params"} else "blocked" if result.status in {"needs_approval", "invalid_params"} else "failed"
        return ExecutionResult(
            status=status,
            backend="app_automation",
            summary=result.message,
            output=result.model_dump(),
            error=result.error.get("message", "") if result.error else "",
            files_touched=[],
        )

    def _get_adapter(self) -> ExecutionAdapter:
        """Resolve the primary adapter; raises RuntimeError if none configured."""
        adapter, _, _, _ = self._route_action("__probe__", {})
        return adapter

    @property
    def backend_name(self) -> str:
        """Return the name of the primary configured backend."""
        if self._backend in ("agentic", "deterministic"):
            return self._backend
        if self._agentic_enabled:
            return "agentic"
        if self._allow_deterministic:
            return "deterministic"
        return "none"
