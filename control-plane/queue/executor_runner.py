"""Run a queued platform task through the selected executor adapter."""

from __future__ import annotations

import sys
from pathlib import Path

CONTROL_PLANE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL_PLANE_DIR))

from executors.base import TaskPacket  # noqa: E402
from executors.direct_executor import DirectExecutor  # noqa: E402
from executors.openhands_adapter import OpenHandsExecutorAdapter  # noqa: E402
from queue.models import PlatformTaskInput, PlatformTaskOutput  # noqa: E402


def run_platform_task(input: PlatformTaskInput) -> PlatformTaskOutput:
    """Execute a platform task synchronously and return a serializable result."""

    packet = TaskPacket(
        task_id=input.task_id,
        session_id=input.session_id,
        instruction=input.instruction,
        worktree_path=input.worktree_path,
        branch=input.branch,
        ui_context=input.ui_context,
        editor_context=input.editor_context,
        terminal_context=input.terminal_context,
        activated_knowledge=input.activated_knowledge,
        staleness_warnings=input.staleness_warnings,
        risk_level=input.risk_level,
        model=input.model,
    )

    if input.executor == "openhands":
        executor = OpenHandsExecutorAdapter()
    elif input.executor == "direct":
        executor = DirectExecutor()
    else:
        raise ValueError(f"Unsupported executor: {input.executor}")

    result = executor.run_task(input.session_id, packet)
    return PlatformTaskOutput(
        status=result.status,
        task_id=input.task_id,
        session_id=input.session_id,
        executor=input.executor,
        files_edited=[str(f) for f in result.files_edited],
        commands_run=[str(c) for c in result.commands_run],
        tests_passed=result.tests_passed,
        tests_failed=result.tests_failed,
        commit_sha=result.commit_sha,
        error=result.error,
        summary=result.summary,
        cost_usd=result.cost_usd,
        duration_seconds=result.duration_seconds,
    )
