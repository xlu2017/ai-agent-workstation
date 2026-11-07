from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.app_automation.models import AppAction, AppAutomationExecuteRequest
from api.app_automation.registry import LOCAL_ADAPTER_FILENAME


@dataclass(frozen=True)
class AdapterHealth:
    vendor: str
    available: bool
    source_path: str
    source_present: bool
    entrypoints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterExecution:
    ok: bool
    status: str
    message: str
    planned_steps: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None


class VendorAdapter:
    vendor_id: str

    def __init__(self, source_path: Path):
        self.source_path = source_path

    def health(self) -> AdapterHealth:
        entrypoints = self.detect_entrypoints()
        notes = []
        if LOCAL_ADAPTER_FILENAME in entrypoints:
            notes.append(f"Local adapter contract file ({LOCAL_ADAPTER_FILENAME}) is available.")
        return AdapterHealth(
            vendor=self.vendor_id,
            available=self.source_path.exists() and any(self.source_path.iterdir()),
            source_path=str(self.source_path),
            source_present=self.source_path.exists(),
            entrypoints=entrypoints,
            notes=notes,
        )

    def detect_entrypoints(self) -> list[str]:
        candidates = [LOCAL_ADAPTER_FILENAME, "package.json", "pyproject.toml", "README.md", "src"]
        return [candidate for candidate in candidates if (self.source_path / candidate).exists()]

    def execute(self, action: AppAction, request: AppAutomationExecuteRequest) -> AdapterExecution:
        if not self.source_path.exists() or not any(self.source_path.iterdir()):
            return AdapterExecution(
                ok=False,
                status="vendor_not_installed",
                message=f"{self.vendor_id} source is not present at {self.source_path}.",
                planned_steps=[f"Expected vendored source at {self.source_path}."],
                error={"code": "VENDOR_NOT_INSTALLED", "message": f"{self.vendor_id} source is not present."},
            )
        from api.app_automation.runtime import execute_vendor_action

        return execute_vendor_action(self.vendor_id, self.source_path, action, request)
