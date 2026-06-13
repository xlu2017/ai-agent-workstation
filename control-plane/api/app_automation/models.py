"""Typed models for app automation catalog and execution."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ExecutionKind = Literal["api", "mcp", "workflow", "browser", "visual_browser", "desktop"]
RiskLevel = Literal["read_only", "modification", "external_side_effect"]
ApprovalMode = Literal["none", "preview", "required"]


class VendorTool(BaseModel):
    id: str
    name: str
    repo_url: str
    target_dir: str
    license: str
    role: str
    priority: int
    execution_kinds: list[ExecutionKind]
    coverage: list[str] = Field(default_factory=list)
    notes: str = ""


class AppAction(BaseModel):
    id: str
    app_id: str
    label: str
    description: str
    execution_kind: ExecutionKind
    preferred_vendor: str
    risk: RiskLevel
    approval: ApprovalMode = "preview"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    available: bool = False
    unavailable_reason: str = "Vendored runtime is not installed yet."


class AppAutomationRouteCandidate(BaseModel):
    rank: int
    vendor: str
    layer: ExecutionKind | str
    installed: bool = False
    target_dir: str | None = None
    reason: str
    status: str


class AppAutomationRoutePlan(BaseModel):
    action_id: str
    app_id: str
    risk: RiskLevel
    approval: ApprovalMode
    preferred_vendor: str
    selected_vendor: str | None = None
    selected_layer: ExecutionKind | str | None = None
    candidates: list[AppAutomationRouteCandidate] = Field(default_factory=list)
    execution_ladder: list[ExecutionKind | str] = Field(default_factory=list)
    coordination_notes: list[str] = Field(default_factory=list)


class AppAutomationExecuteRequest(BaseModel):
    app_id: str
    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    dry_run: bool = True
    approval_granted: bool = False


class AppAutomationExecuteResult(BaseModel):
    ok: bool
    status: str
    vendor: str | None = None
    execution_kind: ExecutionKind | None = None
    app_id: str
    action_id: str
    dry_run: bool = True
    message: str
    planned_steps: list[str] = Field(default_factory=list)
    required_approval: bool = False
    route_plan: AppAutomationRoutePlan | None = None
    event: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
