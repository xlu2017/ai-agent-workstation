from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionKind(str, Enum):
    REPO = "repo"
    APP = "app"
    GOAL = "goal"
    WORK = "work"
    QUESTION = "question"
    VALIDATION = "validation"
    PULL_REQUEST = "pull_request"
    DEPLOYMENT = "deployment"
    ADAPTER = "adapter"
    RUNTIME = "runtime"
    MEMORY = "memory"
    ARTIFACT = "artifact"
    CONTAINER = "container"


class SessionStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    MERGED = "merged"


class EdgeType(str, Enum):
    CONTAINS = "contains"
    COMPONENT_OF = "component_of"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    SIBLING_OF = "sibling_of"
    IMPLEMENTS = "implements"
    VALIDATES = "validates"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    REFERENCES = "references"
    MERGED_INTO = "merged_into"
    FORKED_FROM = "forked_from"
    DELEGATES_TO = "delegates_to"
    MOVED_UNDER = "moved_under"
    MOUNTED_UNDER = "mounted_under"
    ADAPTED_UNDER = "adapted_under"
    ADAPTS_FROM = "adapts_from"
    ADAPTS_INTO = "adapts_into"
    PROJECTS_AS = "projects_as"
    SEMANTIC_ALIAS_OF = "semantic_alias_of"


class MountMode(str, Enum):
    REFERENCE = "reference"
    COMPONENT = "component"
    DEPENDENCY = "dependency"
    VENDOR = "vendor"
    TEMPLATE = "template"
    FORK = "fork"
    PORT = "port"
    WRAP = "wrap"
    COMPARE = "compare"
    UNKNOWN = "unknown"


class ProjectionMode(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    CAPABILITY_MAP = "capability_map"
    FILE_MAP = "file_map"
    API_MAP = "api_map"
    BEHAVIOR_MAP = "behavior_map"
    DIFF_ONLY = "diff_only"
    MEMORY_ONLY = "memory_only"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def model_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class SessionPolicy(BaseModel):
    visibility: str = "workspace"
    allow_mount: bool = True
    allow_adapt: bool = True
    license: str | None = None
    security_constraints: list[str] = Field(default_factory=list)


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: model_id("session"))
    kind: SessionKind
    title: str
    summary: str = ""
    status: SessionStatus = SessionStatus.PROPOSED
    parent_id: str | None = None
    root_id: str | None = None
    facets: dict[str, dict[str, object]] = Field(default_factory=dict)
    policy: SessionPolicy = Field(default_factory=SessionPolicy)
    state: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    created_from_event_id: str | None = None


class SessionEdge(BaseModel):
    id: str = Field(default_factory=lambda: model_id("edge"))
    type: EdgeType
    source_session_id: str
    target_session_id: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    created_from_event_id: str | None = None


class SessionEvent(BaseModel):
    id: str = Field(default_factory=lambda: model_id("event"))
    type: str
    session_id: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class AdapterEndpoint(BaseModel):
    session_id: str
    facet: str | None = None
    path: str | None = None
    symbol: str | None = None
    endpoint: str | None = None
    capability: str | None = None
    description: str


class AdapterMapping(BaseModel):
    id: str = Field(default_factory=lambda: model_id("mapping"))
    source: AdapterEndpoint
    target: AdapterEndpoint
    relationship: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    status: str = "hypothesis"


class AdapterFacet(BaseModel):
    source_session_id: str
    target_session_id: str
    source_role: str
    target_role: str
    preservation_mode: str
    adaptation_mode: str
    mapping_status: str = "proposed"
    mappings: list[AdapterMapping] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)


class ContextProjectionBudget(BaseModel):
    max_tokens: int
    max_files: int
    max_events: int
    recency_days: int | None = None


class ContextProjection(BaseModel):
    id: str = Field(default_factory=lambda: model_id("projection"))
    active_session_id: str
    source_session_ids: list[str]
    projection_mode: ProjectionMode
    include_selectors: list[str] = Field(default_factory=list)
    exclude_selectors: list[str] = Field(default_factory=list)
    budget: ContextProjectionBudget
    rationale: str


class MountSessionRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    user_intent: str
    mount_mode: MountMode
    create_adaptation_session: bool
    make_active: bool = False


class MountSessionResult(BaseModel):
    mounted_edge: SessionEdge
    adaptation_session: SessionRecord | None = None
    adaptation_edges: list[SessionEdge] = Field(default_factory=list)
    context_projection_delta: ContextProjection
    warnings: list[str] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)


class SessionGraphSnapshot(BaseModel):
    sessions: list[SessionRecord] = Field(default_factory=list)
    edges: list[SessionEdge] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)
    projections: list[ContextProjection] = Field(default_factory=list)


class SessionUpdateProposal(BaseModel):
    classification: str
    active_session_id: str | None = None
    created_sessions: list[SessionRecord] = Field(default_factory=list)
    created_edges: list[SessionEdge] = Field(default_factory=list)
    updated_sessions: list[SessionRecord] = Field(default_factory=list)
    mount_request: MountSessionRequest | None = None
    adapter_update: dict[str, object] | None = None
    reason: str
