"""Session graph — settings routes (observability)."""

from __future__ import annotations

from fastapi import APIRouter

from api.services.platform_settings import (
    ObservabilitySettings,
    get_observability_settings,
    update_observability_settings,
)

router = APIRouter()


@router.get("/settings/observability")
def get_observability_settings_endpoint() -> dict[str, dict[str, object]]:
    return {"settings": get_observability_settings().model_dump(mode="json")}


@router.put("/settings/observability")
def update_observability_settings_endpoint(
    body: ObservabilitySettings,
) -> dict[str, dict[str, object]]:
    updated = update_observability_settings(body)
    return {"settings": updated.model_dump(mode="json")}
