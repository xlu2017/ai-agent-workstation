"""Pydantic models for screenshot-guided visual automation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VisualProviderId = Literal[
    "anthropic_computer_use",
    "gemini_computer_use",
    "openai_computer_use",
    "plain_vision_verifier",
]
SurfaceKind = Literal["desktop", "browser", "emulator", "remote_desktop", "unknown"]
VisualTaskKind = Literal["verify_screen_state", "propose_gui_action"]
VisualActionKind = Literal[
    "screenshot",
    "click",
    "double_click",
    "right_click",
    "type",
    "key",
    "scroll",
    "drag",
    "wait",
    "zoom",
    "none",
]
VerificationStatus = Literal["done", "not_done", "blocked", "uncertain"]


class ScreenshotPayload(BaseModel):
    media_type: Literal["image/png", "image/jpeg"] = "image/png"
    base64: str = Field(default="", description="Base64-encoded screenshot payload. Empty is allowed for dry-run tests.")
    width: int | None = None
    height: int | None = None
    source: str | None = Field(default=None, description="guacamole, playwright, emulator, vnc, uploaded, etc.")


class CommandObservation(BaseModel):
    command: str
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None


class RecentVisualAction(BaseModel):
    action: str
    result: str | None = None
    timestamp: str | None = None


class VisualObservationPacket(BaseModel):
    screenshot: ScreenshotPayload | None = None
    terminal_output: str | None = None
    command_history: list[CommandObservation] = Field(default_factory=list)
    ui_text: str | None = None
    dom_snapshot: str | None = None
    accessibility_tree: str | None = None
    recent_actions: list[RecentVisualAction] = Field(default_factory=list)
    active_window: str | None = None
    surface_kind: SurfaceKind = "unknown"
    goal: str
    verification_criteria: list[str] = Field(default_factory=list)


class VisualAction(BaseModel):
    kind: VisualActionKind
    x: int | None = None
    y: int | None = None
    button: Literal["left", "right", "middle"] | None = None
    text: str | None = None
    direction: Literal["up", "down", "left", "right"] | None = None
    amount: int | None = None
    from_xy: tuple[int, int] | None = None
    to_xy: tuple[int, int] | None = None
    duration_seconds: float | None = None
    region: tuple[int, int, int, int] | None = Field(default=None, description="x,y,width,height region for zoom/crop style actions.")


class VisualProviderInfo(BaseModel):
    id: VisualProviderId
    label: str
    default_model: str
    configured: bool
    configured_env: list[str] = Field(default_factory=list)
    best_for: list[SurfaceKind | str] = Field(default_factory=list)
    supports_text_context: bool = True
    supports_terminal_output: bool = True
    supports_coordinates: bool = True
    supports_computer_actions: bool = True
    notes: str = ""


class VerifyScreenRequest(BaseModel):
    provider: VisualProviderId | Literal["auto"] = "auto"
    observation: VisualObservationPacket
    dry_run: bool = True


class VerifyScreenResult(BaseModel):
    ok: bool
    provider: VisualProviderId
    status: VerificationStatus
    evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    message: str
    raw_provider_request: dict[str, Any] | None = None
    raw_provider_response: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ProposeGuiActionRequest(BaseModel):
    provider: VisualProviderId | Literal["auto"] = "auto"
    observation: VisualObservationPacket
    allowed_actions: list[VisualActionKind] = Field(default_factory=lambda: ["click", "type", "key", "scroll", "drag", "wait", "screenshot"])
    require_approval: bool = True
    dry_run: bool = True


class ProposeGuiActionResult(BaseModel):
    ok: bool
    provider: VisualProviderId
    action: VisualAction
    rationale: str
    confidence: float | None = None
    requires_approval: bool = True
    message: str
    raw_provider_request: dict[str, Any] | None = None
    raw_provider_response: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class NormalizeProviderActionRequest(BaseModel):
    provider: VisualProviderId
    raw_provider_response: dict[str, Any]


class NormalizeProviderActionResult(BaseModel):
    ok: bool
    provider: VisualProviderId
    actions: list[VisualAction] = Field(default_factory=list)
    message: str
    error: dict[str, Any] | None = None
