"""Repository source registry routes.

These routes make repository identity editable data. The credential provider is
selected separately through /api/repo-provider/*.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.repo_source_registry import (
    get_repo_source,
    list_repo_sources,
    reset_repo_source,
    update_repo_source,
)

router = APIRouter(prefix="/api/repo-sources", tags=["repo-sources"])


class RepoSourcePatch(BaseModel):
    enabled: bool | None = None
    repo_provider: str | None = Field(default=None, description="Source host provider such as github.")
    owner: str | None = None
    repo: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    path: str | None = None
    install_commands: list[str] | None = None
    build_commands: list[str] | None = None
    restart_command: str | None = None

    def patch(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


@router.get("")
def repo_sources() -> dict[str, object]:
    """List service-to-repository mappings used by update/check operations."""
    return {"services": list_repo_sources()}


@router.get("/{service_name}")
def repo_source(service_name: str) -> dict[str, object]:
    source = get_repo_source(service_name)
    if source is None:
        raise HTTPException(404, {"ok": False, "error": {"code": "UNKNOWN_SERVICE", "message": f"No repo source is configured for {service_name}."}})
    return {"service": source}


@router.put("/{service_name}")
def repo_source_update(service_name: str, body: RepoSourcePatch) -> dict[str, object]:
    """Update owner/repo/branch/path data for a repo-backed service."""
    source = update_repo_source(service_name, body.patch())
    return {"ok": True, "service": source}


@router.post("/{service_name}/reset")
def repo_source_reset(service_name: str) -> dict[str, object]:
    try:
        source = reset_repo_source(service_name)
    except KeyError:
        raise HTTPException(404, {"ok": False, "error": {"code": "UNKNOWN_SERVICE", "message": f"No default repo source exists for {service_name}."}})
    return {"ok": True, "service": source}
