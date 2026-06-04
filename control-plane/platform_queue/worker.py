"""Hatchet worker process for platform session tasks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platform_queue.hatchet_client import hatchet  # noqa: E402
from platform_queue.hatchet_tasks import platform_session_task  # noqa: E402


def main() -> None:
    name = os.environ.get("PLATFORM_HATCHET_WORKER_NAME", "platform-session-worker")
    slots = int(os.environ.get("PLATFORM_HATCHET_WORKER_SLOTS", "2"))
    worker = hatchet.worker(name, slots=slots, workflows=[platform_session_task])
    worker.start()


if __name__ == "__main__":
    main()
