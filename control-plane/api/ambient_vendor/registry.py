"""Thin wrapper exposing the ambient vendor registry via Pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ambient.vendor_registry import (
    get_vendor as _get_vendor,
    list_vendors as _list_vendors,
    load_manifest,
)
from api.ambient_vendor.models import VendorToolEntry


def list_vendor_entries(manifest_path: Path | None = None) -> list[VendorToolEntry]:
    return [VendorToolEntry(**v) for v in _list_vendors(manifest_path)]


def get_vendor_entry(tool_id: str, manifest_path: Path | None = None) -> VendorToolEntry | None:
    raw = _get_vendor(tool_id, manifest_path)
    return VendorToolEntry(**raw) if raw else None


def tool_ids(manifest_path: Path | None = None) -> list[str]:
    manifest = load_manifest(manifest_path)
    return [t["id"] for t in manifest.get("selected_tools", [])]
