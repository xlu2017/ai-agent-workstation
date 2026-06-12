from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTROL_PLANE_ROOT.parent
MANIFEST_PATH = CONTROL_PLANE_ROOT / "vendor" / "ambient-context" / "manifest.json"


@dataclass(frozen=True)
class AmbientVendor:
    id: str
    name: str
    repo_url: str
    target_dir: str
    role: str
    collector_targets: list[str]
    python_path_hints: list[str]
    metadata: dict[str, Any]

    @property
    def source_path(self) -> Path:
        return REPO_ROOT / self.target_dir

    @property
    def source_present(self) -> bool:
        path = self.source_path
        return path.exists() and any(path.iterdir())

    def candidate_python_paths(self) -> list[Path]:
        source = self.source_path
        candidates = [source, source / "src", source / "python", source / "packages"]
        candidates.extend(path for path in source.glob("*/src") if path.is_dir()) if source.exists() else None
        return [path for path in candidates if path.exists()]

    def module_available(self) -> bool:
        for path in self.candidate_python_paths():
            path_text = str(path)
            if path_text not in sys.path:
                sys.path.insert(0, path_text)
        for module_name in self.python_path_hints:
            if importlib.util.find_spec(module_name) is not None:
                return True
        return not self.python_path_hints and self.source_present

    def status(self) -> dict[str, Any]:
        fetched_metadata_path = self.source_path / "VENDORED_METADATA.json"
        fetched_metadata: dict[str, Any] = {}
        if fetched_metadata_path.exists():
            try:
                fetched_metadata = json.loads(fetched_metadata_path.read_text())
            except (OSError, json.JSONDecodeError):
                fetched_metadata = {"metadata_error": "failed_to_read"}
        return {
            "id": self.id,
            "name": self.name,
            "repo_url": self.repo_url,
            "target_dir": self.target_dir,
            "source_present": self.source_present,
            "candidate_python_paths": [str(path) for path in self.candidate_python_paths()],
            "module_available": self.module_available(),
            "role": self.role,
            "collector_targets": self.collector_targets,
            "python_path_hints": self.python_path_hints,
            "fetched_metadata": fetched_metadata,
        }


def load_ambient_vendor_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"version": 0, "intent": "ambient vendor manifest missing", "selected_tools": []}
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"version": 0, "intent": "ambient vendor manifest unreadable", "selected_tools": []}


def list_ambient_vendors() -> list[AmbientVendor]:
    manifest = load_ambient_vendor_manifest()
    vendors: list[AmbientVendor] = []
    for raw in manifest.get("selected_tools", []):
        if not isinstance(raw, dict):
            continue
        vendors.append(
            AmbientVendor(
                id=str(raw.get("id", "")),
                name=str(raw.get("name", raw.get("id", ""))),
                repo_url=str(raw.get("repo_url", "")),
                target_dir=str(raw.get("target_dir", "")),
                role=str(raw.get("role", "")),
                collector_targets=list(raw.get("collector_targets", [])),
                python_path_hints=list(raw.get("python_path_hints", [])),
                metadata=raw,
            )
        )
    return [vendor for vendor in vendors if vendor.id and vendor.target_dir]


def get_ambient_vendor(vendor_id: str) -> AmbientVendor | None:
    for vendor in list_ambient_vendors():
        if vendor.id == vendor_id:
            return vendor
    return None


def ambient_vendor_status() -> dict[str, Any]:
    manifest = load_ambient_vendor_manifest()
    vendors = list_ambient_vendors()
    return {
        "version": manifest.get("version", 0),
        "intent": manifest.get("intent", ""),
        "vendors": [vendor.status() for vendor in vendors],
        "collector_targets": _collector_target_map(vendors),
    }


def _collector_target_map(vendors: list[AmbientVendor]) -> dict[str, list[str]]:
    target_map: dict[str, list[str]] = {}
    for vendor in vendors:
        for target in vendor.collector_targets:
            target_map.setdefault(target, []).append(vendor.id)
    return target_map


def ensure_vendor_python_path(vendor_id: str) -> Path | None:
    """Add vendored source paths to sys.path when present.

    Vendored code is treated as repository-owned implementation code, but it is
    still optional at import time so the server can boot before every vendor is
    cloned or built.
    """

    vendor = get_ambient_vendor(vendor_id)
    if not vendor or not vendor.source_present:
        return None
    for path in vendor.candidate_python_paths():
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    return vendor.source_path


def provider_available(vendor_id: str, module_name: str | None = None) -> bool:
    ensure_vendor_python_path(vendor_id)
    if module_name:
        return importlib.util.find_spec(module_name) is not None
    vendor = get_ambient_vendor(vendor_id)
    return bool(vendor and vendor.module_available())
