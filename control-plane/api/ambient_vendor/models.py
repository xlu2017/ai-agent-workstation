"""Typed models for ambient-context vendor operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VendorToolEntry(BaseModel):
    id: str
    name: str
    repo_url: str
    github_owner: str = ""
    github_repo: str = ""
    target_dir: str
    role: str = ""
    collector_targets: list[str] = Field(default_factory=list)
    source_present: bool = False
    fetched_metadata: dict[str, Any] | None = None


class VendorFetchResult(BaseModel):
    ok: bool
    tool_id: str
    source_present: bool = False
    target_dir: str = ""
    fetched_ref: str | None = None
    fetched_at: str | None = None
    message: str = ""
    error: dict[str, Any] | None = None


class VendorFetchRequest(BaseModel):
    ref: str | None = None
    force: bool = False


class VendorAuthError(BaseModel):
    ok: bool = False
    error: dict[str, Any] = Field(default_factory=lambda: {
        "code": "GITHUB_AUTH_REQUIRED",
        "message": "Configure GitHub login or GITHUB_TOKEN before fetching ambient vendors.",
    })
