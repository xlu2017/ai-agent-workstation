"""
HatchetWorkflowAdapter — production durable workflow execution via Hatchet.

Hatchet owns durable session/plan workflows and action queuing.
LangGraph is NOT the workflow runner — it is used inside Hatchet steps
for composite action subflows only.

Import is lazy: Hatchet SDK is only loaded when this adapter is constructed.
If unavailable and fallback is not explicitly enabled, raises RuntimeError.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from adapters.workflow.base import WorkflowAdapter

HATCHET_ENABLED = os.environ.get("HATCHET_ENABLED", "true").lower() == "true"
HATCHET_SERVER_URL = os.environ.get("HATCHET_SERVER_URL", "")
HATCHET_CLIENT_TOKEN = os.environ.get("HATCHET_CLIENT_TOKEN", "")


def _import_hatchet():
    """Lazy import of the Hatchet SDK."""
    try:
        import hatchet_sdk
        return hatchet_sdk
    except ImportError:
        return None


class HatchetWorkflowAdapter(WorkflowAdapter):
    """Durable workflow execution via Hatchet.

    Starts the execute_agent_plan workflow in Hatchet.
    Supports pause/resume/cancel via session state control intents
    (Hatchet does not natively support pause semantics in all SDK versions).
    """

    def __init__(self):
        self._hatchet_sdk = _import_hatchet()
        if self._hatchet_sdk is None:
            raise RuntimeError(
                "Hatchet SDK is not installed. Install hatchet-sdk or set "
                "WORKFLOW_BACKEND=inprocess for dev/test mode."
            )
        self._client = self._hatchet_sdk.Hatchet()
        # Track control intents per session (for SDKs without native pause)
        self._control_intents: dict[str, str] = {}

    async def start_plan(
        self, session_id: str, plan: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        workflow_input = {
            "session_id": session_id,
            "plan": plan,
            "context": context,
        }
        try:
            workflow_run = self._client.admin.run_workflow(
                "execute_agent_plan",
                workflow_input,
            )
            run_id = getattr(workflow_run, "workflow_run_id", str(uuid.uuid4()))
            return {
                "started": True,
                "backend": "hatchet",
                "session_id": session_id,
                "workflow_run_id": run_id,
            }
        except Exception as e:
            return {
                "started": False,
                "backend": "hatchet",
                "session_id": session_id,
                "error": str(e),
            }

    async def pause(self, session_id: str) -> dict[str, Any]:
        self._control_intents[session_id] = "pause"
        return {
            "accepted": True,
            "backend": "hatchet",
            "session_id": session_id,
            "mechanism": "session_state_control_intent",
        }

    async def resume(self, session_id: str) -> dict[str, Any]:
        self._control_intents.pop(session_id, None)
        return {
            "accepted": True,
            "backend": "hatchet",
            "session_id": session_id,
            "mechanism": "session_state_control_intent",
        }

    async def cancel(self, session_id: str) -> dict[str, Any]:
        self._control_intents[session_id] = "cancel"
        return {
            "accepted": True,
            "backend": "hatchet",
            "session_id": session_id,
            "mechanism": "session_state_control_intent",
        }

    async def status(self, session_id: str) -> dict[str, Any]:
        intent = self._control_intents.get(session_id, "running")
        return {
            "backend": "hatchet",
            "session_id": session_id,
            "control_intent": intent,
        }

    def get_control_intent(self, session_id: str) -> str:
        """Check if there is a pending control intent for a session."""
        return self._control_intents.get(session_id, "")
