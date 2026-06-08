"""Hatchet task definitions for platform agent-session execution."""

from __future__ import annotations

from datetime import timedelta

from hatchet_sdk import Context

from platform_queue.executor_runner import run_platform_task
from platform_queue.hatchet_client import hatchet
from platform_queue.models import PlatformTaskInput, PlatformTaskOutput


@hatchet.task(
    name="platform-session-task",
    input_validator=PlatformTaskInput,
    execution_timeout=timedelta(minutes=90),
    retries=0,
)
def platform_session_task(input: PlatformTaskInput, ctx: Context) -> PlatformTaskOutput:
    """Run one platform session task through the agentic or deterministic executor."""

    return run_platform_task(input)
