"""Visual model provider routes for screenshot-guided automation."""

from __future__ import annotations

from fastapi import APIRouter

from api.visual_automation.models import (
    NormalizeProviderActionRequest,
    ProposeGuiActionRequest,
    VerifyScreenRequest,
)
from api.visual_automation.providers import list_visual_providers
from api.visual_automation.service import normalize_action_request, propose_gui_action, verify_screen_state

router = APIRouter(prefix="/api/visual-automation", tags=["visual-automation"])


@router.get("/providers")
def visual_providers() -> dict:
    """Return supported visual providers and credential/configuration status."""
    return {"providers": [provider.model_dump() for provider in list_visual_providers()]}


@router.post("/verify-screen")
def verify_screen(body: VerifyScreenRequest) -> dict:
    """Verify whether a screenshot/text observation satisfies the requested goal."""
    return verify_screen_state(body).model_dump()


@router.post("/propose-action")
def propose_action(body: ProposeGuiActionRequest) -> dict:
    """Propose the next GUI action from a screenshot/text observation."""
    return propose_gui_action(body).model_dump()


@router.post("/normalize-action")
def normalize_action(body: NormalizeProviderActionRequest) -> dict:
    """Normalize provider-specific computer-use output into platform visual actions."""
    return normalize_action_request(body).model_dump()
