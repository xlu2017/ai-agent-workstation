"""Ambient context vendor registry.

Loads the vendor manifest, reports whether source/ exists for each tool,
exposes collector-target mappings, and reads fetched metadata when present.
Does not import vendored source directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = CONTROL_PLANE_ROOT / "vendor" / "ambient-context" / "manifest.json"


def load_manifest(manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or MANIFEST_PATH
    with path.open() as f:
        return json.load(f)


def _tool_source_dir(tool: dict[str, Any], manifest_path: Path | None = None) -> Path:
    root = (manifest_path or MANIFEST_PATH).resolve().parents[2]
    return root / tool["target_dir"]


def _fetched_metadata_path(source_dir: Path) -> Path:
    return source_dir.parent / "fetched_metadata.json"


def source_present(tool: dict[str, Any], manifest_path: Path | None = None) -> bool:
    source_dir = _tool_source_dir(tool, manifest_path)
    children = [p for p in source_dir.iterdir() if p.name != ".gitkeep"] if source_dir.exists() else []
    return len(children) > 0


def fetched_metadata(tool: dict[str, Any], manifest_path: Path | None = None) -> dict[str, Any] | None:
    source_dir = _tool_source_dir(tool, manifest_path)
    meta_path = _fetched_metadata_path(source_dir)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except Exception:
        return None


def list_vendors(manifest_path: Path | None = None) -> list[dict[str, Any]]:
    manifest = load_manifest(manifest_path)
    results = []
    for tool in manifest.get("selected_tools", []):
        meta = fetched_metadata(tool, manifest_path)
        results.append({
            "id": tool["id"],
            "name": tool["name"],
            "repo_url": tool["repo_url"],
            "github_owner": tool.get("github_owner", ""),
            "github_repo": tool.get("github_repo", ""),
            "target_dir": tool["target_dir"],
            "role": tool.get("role", ""),
            "collector_targets": tool.get("collector_targets", []),
            "source_present": source_present(tool, manifest_path),
            "fetched_metadata": meta,
        })
    return results


def get_vendor(tool_id: str, manifest_path: Path | None = None) -> dict[str, Any] | None:
    for vendor in list_vendors(manifest_path):
        if vendor["id"] == tool_id:
            return vendor
    return None


def collector_target_map(manifest_path: Path | None = None) -> dict[str, list[str]]:
    """Return {tool_id: [collector_target, ...]} for all vendors."""
    manifest = load_manifest(manifest_path)
    return {
        tool["id"]: tool.get("collector_targets", [])
        for tool in manifest.get("selected_tools", [])
    }
