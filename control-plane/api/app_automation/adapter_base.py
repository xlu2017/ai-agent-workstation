from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.app_automation.models import AppAction, AppAutomationExecuteRequest


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
        return AdapterHealth(
            vendor=self.vendor_id,
            available=self.source_path.exists() and any(self.source_path.iterdir()),
            source_path=str(self.source_path),
            source_present=self.source_path.exists(),
            entrypoints=self.detect_entrypoints(),
        )

    def detect_entrypoints(self) -> list[str]:
        candidates = ["package.json", "pyproject.toml", "README.md", "src"]
        return [candidate for candidate in candidates if (self.source_path / candidate).exists()]

    def execute(self, action: AppAction, request: AppAutomationExecuteRequest) -> AdapterExecution:
        return AdapterExecution(
            ok=False,
            status="adapter_scaffolded",
            message=f"{self.vendor_id} source is present; live adapter execution for {action.id} is scaffolded but not enabled.",
            planned_steps=[
                f"Load vendored source from {self.source_path}.",
                f"Map platform action {action.id} to {self.vendor_id} runtime.",
                "Keep platform policy and approvals outside the vendored runtime.",
            ],
            error={"code": "ADAPTER_SCAFFOLDED", "message": "Live vendor execution is scaffolded but not enabled."},
        )
