from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from execution.ambient_prompt_context import (
    ambient_packet_to_agent_core_context,
    ambient_packet_to_prompt_block,
    load_ambient_context_packet,
)

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))

router = APIRouter(prefix="/api/sessions/{session_id}/recommendations", tags=["session-recommendations"])


class RecommendNextRequest(BaseModel):
    task_type: str = "implementation"
    current_action: str = ""
    completed_actions: list[str] = Field(default_factory=list)
    repo_id: str = ""
    visible_actions: list[str] = Field(default_factory=list)
    include_prompt_block: bool = True


@router.post("/next-action")
async def recommend_next_action(session_id: str, body: RecommendNextRequest):
    """Return one advisory next-action recommendation with ambient context.

    This route does not execute the recommendation. It packages the current
    session ambient context and sends it to agent-core's recommend-next endpoint,
    then annotates the response with the local ambient context summary used.
    """

    packet = load_ambient_context_packet(
        session_id,
        goal=body.current_action or body.task_type,
        sessions_dir=SESSIONS_DIR,
    )
    ambient_context = ambient_packet_to_agent_core_context(packet)
    prompt_block = ambient_packet_to_prompt_block(packet) if body.include_prompt_block else ""

    try:
        from agent_core_client.client import AgentCoreClient

        client = AgentCoreClient()
        try:
            response = await client.recommend_next(
                task_type=body.task_type,
                current_action=body.current_action,
                completed_actions=body.completed_actions,
                session_id=session_id,
                repo_id=body.repo_id,
                ambient_context=ambient_context,
                visible_actions=body.visible_actions or None,
            )
        finally:
            await client.close()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "agent-core recommend-next unavailable",
                "message": str(exc),
                "ambient_context": ambient_context,
                "prompt_block": prompt_block,
                "visible_actions": body.visible_actions,
                "advisory_only": True,
                "requires_platform_validation": True,
            },
        ) from exc

    return {
        "session_id": session_id,
        "recommendation": response,
        "ambient_context": ambient_context,
        "prompt_block": prompt_block,
        "visible_actions": body.visible_actions,
        "advisory_only": True,
        "requires_platform_validation": True,
    }
