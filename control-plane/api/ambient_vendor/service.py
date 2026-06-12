"""Ambient vendor fetch service.

Orchestrates server-side GitHub archive download into vendor target directories.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from ambient.vendor_registry import load_manifest, source_present
from api.ambient_vendor.github_fetcher import (
    extract_zipball,
    fetch_zipball,
    write_fetched_metadata,
    write_vendored_patches,
)
from api.ambient_vendor.models import VendorAuthError, VendorFetchResult

logger = logging.getLogger(__name__)

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[2]


def _get_token() -> str | None:
    """Resolve a GitHub token using the repo-provider auth layer or env fallback."""
    try:
        from api.repo_provider import get_repo_provider_token
        token = get_repo_provider_token()
        if token:
            return token
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT") or os.environ.get("PAT")


def _resolve_tool(tool_id: str, manifest_path: Path | None = None) -> dict[str, Any] | None:
    manifest = load_manifest(manifest_path)
    for tool in manifest.get("selected_tools", []):
        if tool["id"] == tool_id:
            return tool
    return None


def _target_dir(tool: dict[str, Any], manifest_path: Path | None = None) -> Path:
    root = (manifest_path or CONTROL_PLANE_ROOT / "vendor" / "ambient-context" / "manifest.json").resolve().parents[2]
    return root / tool["target_dir"]


def _has_uncommitted_content(target: Path) -> bool:
    """Check whether target_dir has real files (beyond .gitkeep)."""
    if not target.exists():
        return False
    children = [p for p in target.iterdir() if p.name != ".gitkeep"]
    return len(children) > 0


def fetch_vendor(
    tool_id: str,
    ref: str | None = None,
    force: bool = False,
    manifest_path: Path | None = None,
) -> VendorFetchResult:
    token = _get_token()
    if not token:
        err = VendorAuthError()
        return VendorFetchResult(
            ok=False,
            tool_id=tool_id,
            message=err.error["message"],
            error=err.error,
        )

    tool = _resolve_tool(tool_id, manifest_path)
    if not tool:
        return VendorFetchResult(
            ok=False,
            tool_id=tool_id,
            message=f"Unknown tool_id: {tool_id}",
            error={"code": "UNKNOWN_TOOL", "message": f"Tool '{tool_id}' not in manifest."},
        )

    target = _target_dir(tool, manifest_path)

    if _has_uncommitted_content(target) and not force:
        return VendorFetchResult(
            ok=False,
            tool_id=tool_id,
            target_dir=str(tool["target_dir"]),
            source_present=True,
            message="Target directory already contains content. Use force=true to overwrite.",
            error={"code": "TARGET_NOT_EMPTY", "message": "Use force=true to overwrite existing source."},
        )

    owner = tool.get("github_owner", "")
    repo = tool.get("github_repo", "")
    if not owner or not repo:
        return VendorFetchResult(
            ok=False,
            tool_id=tool_id,
            message="Tool manifest entry missing github_owner/github_repo.",
            error={"code": "INVALID_MANIFEST", "message": "Missing github_owner or github_repo."},
        )

    try:
        zip_bytes, metadata = fetch_zipball(owner, repo, token, ref=ref)
    except RuntimeError as exc:
        return VendorFetchResult(
            ok=False,
            tool_id=tool_id,
            target_dir=str(tool["target_dir"]),
            message=str(exc),
            error={"code": "FETCH_FAILED", "message": str(exc)},
        )

    if target.exists() and force:
        for child in target.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    count = extract_zipball(zip_bytes, target)
    write_fetched_metadata(target, metadata)
    write_vendored_patches(target, tool["name"], tool["repo_url"])

    logger.info("Fetched %s: %d files into %s", tool_id, count, target)

    return VendorFetchResult(
        ok=True,
        tool_id=tool_id,
        source_present=True,
        target_dir=str(tool["target_dir"]),
        fetched_ref=metadata.get("fetched_ref"),
        fetched_at=metadata.get("fetched_at"),
        message=f"Fetched {count} files from {owner}/{repo}.",
    )


def fetch_all_vendors(
    ref: str | None = None,
    force: bool = False,
    manifest_path: Path | None = None,
) -> list[VendorFetchResult]:
    manifest = load_manifest(manifest_path)
    results = []
    for tool in manifest.get("selected_tools", []):
        result = fetch_vendor(tool["id"], ref=ref, force=force, manifest_path=manifest_path)
        results.append(result)
    return results
