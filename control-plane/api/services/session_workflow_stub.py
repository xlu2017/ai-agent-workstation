from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionWorkflowRun:
    session_id: str
    workflow_name: str
    payload: dict[str, object] = field(default_factory=dict)


class SessionWorkflowDispatcher:
    def enqueue(self, run: SessionWorkflowRun) -> dict[str, object]:
        return {
            "queued": False,
            "workflow_name": run.workflow_name,
            "session_id": run.session_id,
            "reason": "Durable workflow backend is not configured in this scaffold.",
        }
