from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from api.models.session_graph import utc_now


def mf_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class OperatingSystemFamily(str, Enum):
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"


class FrontendRuntimeKind(str, Enum):
    BROWSER = "browser"
    EMULATOR = "emulator"
    SIMULATOR = "simulator"
    WEBVIEW = "webview"
    DESKTOP_APP = "desktop_app"


class InstanceHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    STOPPED = "stopped"


class StateIsolationMode(str, Enum):
    SHARED_BACKEND_SHARED_USER = "shared_backend_shared_user"
    SHARED_BACKEND_SEPARATE_USER = "shared_backend_separate_user"
    SHARED_BACKEND_SEPARATE_TENANT = "shared_backend_separate_tenant"
    ISOLATED_BACKEND = "isolated_backend"


class DeviceProfile(BaseModel):
    id: str = Field(default_factory=lambda: mf_id("device"))
    label: str
    os_family: OperatingSystemFamily
    runtime_kind: FrontendRuntimeKind
    viewport_width: int | None = None
    viewport_height: int | None = None
    device_scale_factor: float | None = None
    user_agent: str | None = None
    emulator_name: str | None = None
    browser_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class BackendInstance(BaseModel):
    id: str = Field(default_factory=lambda: mf_id("backend"))
    session_id: str | None = None
    label: str
    base_url: str
    health: InstanceHealth = InstanceHealth.UNKNOWN
    port: int | None = None
    process_id: int | None = None
    log_stream_id: str | None = None
    trace_service_url: str | None = None
    route_map_ref: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class FrontendInstance(BaseModel):
    id: str = Field(default_factory=lambda: mf_id("frontend"))
    session_id: str | None = None
    label: str
    device_profile: DeviceProfile
    backend_instance_id: str
    target_base_url: str
    health: InstanceHealth = InstanceHealth.UNKNOWN
    current_url: str | None = None
    browser_profile_id: str | None = None
    emulator_id: str | None = None
    auth_identity: str | None = None
    tenant_id: str | None = None
    latest_trace_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TraceCorrelationHeaders(BaseModel):
    root_session_id: str
    backend_session_id: str
    frontend_session_id: str
    frontend_instance_id: str
    device_profile_id: str
    user_flow_id: str | None = None
    trace_id: str | None = None


class CrossClientTrace(BaseModel):
    id: str = Field(default_factory=lambda: mf_id("trace"))
    root_session_id: str
    backend_instance_id: str
    frontend_instance_id: str
    trace_id: str
    method: str | None = None
    url: str | None = None
    status_code: int | None = None
    backend_route: str | None = None
    user_flow_id: str | None = None
    created_at: str = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(default_factory=dict)


class MultiFrontendTopology(BaseModel):
    root_session_id: str
    backend: BackendInstance
    frontends: list[FrontendInstance] = Field(default_factory=list)
    isolation_mode: StateIsolationMode = StateIsolationMode.SHARED_BACKEND_SEPARATE_USER
    traces: list[CrossClientTrace] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class CreateMultiFrontendTopologyRequest(BaseModel):
    app_title: str
    intent: str = "Coordinate multiple frontend clients against one backend."
    backend: BackendInstance
    frontends: list[FrontendInstance]
    isolation_mode: StateIsolationMode = StateIsolationMode.SHARED_BACKEND_SEPARATE_USER
    metadata: dict[str, object] = Field(default_factory=dict)


class RegisterCrossClientTraceRequest(BaseModel):
    root_session_id: str
    backend_instance_id: str
    frontend_instance_id: str
    trace_id: str
    method: str | None = None
    url: str | None = None
    status_code: int | None = None
    backend_route: str | None = None
    user_flow_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class FrontendMatrixRow(BaseModel):
    frontend_instance_id: str
    frontend_session_id: str | None = None
    label: str
    os_family: OperatingSystemFamily
    runtime_kind: FrontendRuntimeKind
    health: InstanceHealth
    current_url: str | None = None
    latest_trace_id: str | None = None
    auth_identity: str | None = None
    tenant_id: str | None = None


class MultiFrontendMatrix(BaseModel):
    root_session_id: str
    backend_session_id: str | None = None
    backend_label: str
    backend_base_url: str
    backend_health: InstanceHealth
    isolation_mode: StateIsolationMode
    frontends: list[FrontendMatrixRow] = Field(default_factory=list)
    trace_count: int = 0
    updated_at: str = Field(default_factory=utc_now)
