"""Queue submitter for platform tasks.

This module prefers Hatchet when available. If Hatchet is not configured or the
SDK call shape changes, it records a local queued job under /opt/workstation/tasks
so the control plane can still persist the user's intent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_queue.models import PlatformTaskInput, QueueSubmitResult

TASKS_DIR = Path("/opt/workstation/tasks")


def submit_platform_task(input: PlatformTaskInput) -> QueueSubmitResult:
    """Submit a task to Hatchet, falling back to durable local metadata."""

    try:
        from platform_queue.hatchet_tasks import platform_session_task

        # Hatchet SDK examples expose task.run() for fire-and-forget execution in
        # current releases. Keep this isolated so SDK drift only affects this file.
        run = platform_session_task.run(input.model_dump())  # type: ignore[attr-defined]
        run_id = _extract_run_id(run)
        _write_submit_record(input, "hatchet", run_id=run_id)
        return QueueSubmitResult(
            queued=True,
            queue_backend="hatchet",
            task_id=input.task_id,
            session_id=input.session_id,
            run_id=run_id,
            message="Queued on Hatchet.",
        )
    except Exception as e:
        run_id = f"local-{uuid.uuid4()}"
        _write_submit_record(input, "local", run_id=run_id, error=str(e))
        return QueueSubmitResult(
            queued=True,
            queue_backend="local",
            task_id=input.task_id,
            session_id=input.session_id,
            run_id=run_id,
            message=f"Hatchet unavailable; recorded local queued task: {e}",
        )


def _extract_run_id(run: Any) -> str | None:
    for attr in ("workflow_run_id", "run_id", "id"):
        value = getattr(run, attr, None)
        if value:
            return str(value)
    if isinstance(run, dict):
        for key in ("workflow_run_id", "run_id", "id"):
            if run.get(key):
                return str(run[key])
    return None


def _write_submit_record(
    input: PlatformTaskInput,
    backend: str,
    run_id: str | None,
    error: str | None = None,
) -> None:
    task_dir = TASKS_DIR / input.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": input.task_id,
        "session_id": input.session_id,
        "queue_backend": backend,
        "run_id": run_id,
        "error": error,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "input": input.model_dump(),
    }
    (task_dir / "queue.json").write_text(json.dumps(payload, indent=2))
