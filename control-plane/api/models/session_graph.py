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
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    MERGED = "merged"
    ARCHIVED = "archived"


class SessionFacetName(str, Enum):
    REPO = "repo"
    APP = "app"
    GOAL = "goal"
    WORK = "work"
    ADAPTER = "adapter"
    RUNTIME = "runtime"
    VALIDATION = "validation"
    MEMORY = "memory"
    ARTIFACT = "artifact"
    PULL_REQUEST = "pull_request"
    DEPLOYMENT = "deployment"


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
    DEPRECATED_MOVED_UNDER = "deprecated_moved_under"
    MOUNTED_UNDER = "mounted_under"
    ADAPTED_UNDER = "adapted_under"
    ADAPTS_FROM = "adapts_from"
    ADAPTS_INTO = "adapts_into"
    PROJECTS_AS = "projects_as"
    SEMANTIC_ALIAS_OF = "semantic_alias_of"


class SessionEventType(str, Enum):
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    SESSION_LINKED = "session.linked"
    SESSION_UNLINKED = "session.unlinked"
    SESSION_MOUNTED = "session.mounted"
    SESSION_UNMOUNTED = "session.unmounted"
    SESSION_ADAPTER_CREATED = "session.adapter_created"
    SESSION_ADAPTER_MAPPING_ADDED = "session.adapter_mapping_added"
    SESSION_ADAPTER_MAPPING_CONFIRMED = "session.adapter_mapping_confirmed"
    SESSION_ADAPTER_PROJECTION_CREATED = "session.adapter_projection_created"
    SESSION_ADAPTER_WARNING_ADDED = "session.adapter_warning_added"
    SESSION_MERGED = "session.merged"
    SESSION_FORKED = "session.forked"
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    GOAL_SUPERSEDED = "goal.superseded"
    WORK_STARTED = "work.started"
    WORK_PAUSED = "work.paused"
    WORK_COMPLETED = "work.completed"
    ACTION_PROPOSED = "action.proposed"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    OBSERVATION_RECORDED = "observation.recorded"
    ARTIFACT_CREATED = "artifact.created"
    VALIDATION_STARTED = "validation.started"
    VALIDATION_COMPLETED = "validation.completed"
    POLICY_BLOCKED = "policy.blocked"
    USER_INTERJECTED = "user.interjected"


class SessionEventActor(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    EXECUTOR = "executor"


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


class ProjectionSource(str, Enum):
    HEURISTIC = "heuristic"
    MAPPING_BASED = "mapping_based"
    RETRIEVAL_BASED = "retrieval_based"


class ProjectionSelector(str, Enum):
    SUMMARY = "summary"
    FACETS = "facets"
    RELATIONSHIPS = "relationships"
    CAPABILITIES = "capabilities"
    BEHAVIORS = "behaviors"
    INTERFACES = "interfaces"
    RELEVANT_FILES = "relevant_files"
    TERMINATION_CONDITIONS = "termination_conditions"
    ADAPTER_MAPPINGS = "adapter_mappings"
    SUCCESS_CRITERIA = "success_criteria"
    KNOWN_COMMANDS = "known_commands"
    KNOWN_PATHS = "known_paths"
    API_CONTRACTS = "api_contracts"
    SECURITY_CONSTRAINTS = "security_constraints"
    UNRELATED_UI = "unrelated_ui"
    DEPLOYMENT = "deployment"
    PLUGINS = "plugins"
    HISTORICAL_NOISE = "historical_noise"
    UNRELATED_CAPABILITIES = "unrelated_capabilities"


class PolicyVisibility(str, Enum):
    PUBLIC = "public"
    WORKSPACE = "workspace"
    PRIVATE = "private"


class AdapterSourceRole(str, Enum):
    REFERENCE_IMPLEMENTATION = "reference_implementation"
    VENDOR_DEPENDENCY = "vendor_dependency"
    RUNTIME_BACKEND = "runtime_backend"
    DESIGN_PATTERN_SOURCE = "design_pattern_source"
    CODE_SOURCE = "code_source"
    DOCUMENTATION_SOURCE = "documentation_source"
    TEST_SOURCE = "test_source"
    MIGRATION_SOURCE = "migration_source"
    COMPARISON_BASELINE = "comparison_baseline"


class AdapterTargetRole(str, Enum):
    CAPABILITY_TO_INTEGRATE = "capability_to_integrate"
    COMPONENT_TO_WRAP = "component_to_wrap"
    COMPONENT_TO_PORT = "component_to_port"
    ARCHITECTURE_TO_EMULATE = "architecture_to_emulate"
    BEHAVIOR_TO_MATCH = "behavior_to_match"
    DEPENDENCY_TO_CALL = "dependency_to_call"
    KNOWLEDGE_SOURCE = "knowledge_source"


class PreservationMode(str, Enum):
    LOSSLESS_REFERENCE = "lossless_reference"
    COPY_SNAPSHOT = "copy_snapshot"
    FORK = "fork"
    VENDOR_IMPORT = "vendor_import"
    PORT = "port"
    WRAP = "wrap"
    REIMPLEMENT = "reimplement"


class AdaptationMode(str, Enum):
    SEMANTIC_PROJECTION = "semantic_projection"
    INTERFACE_MAPPING = "interface_mapping"
    CAPABILITY_MAPPING = "capability_mapping"
    FILE_MAPPING = "file_mapping"
    API_MAPPING = "api_mapping"
    BEHAVIOR_MAPPING = "behavior_mapping"
    MIGRATION_PLAN = "migration_plan"


class AdapterMappingStatus(str, Enum):
    PROPOSED = "proposed"
    MAPPING = "mapping"
    MAPPED = "mapped"
    PARTIALLY_INTEGRATED = "partially_integrated"
    INTEGRATED = "integrated"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


class AdapterRelationship(str, Enum):
    SAME_CONCEPT = "same_concept"
    SIMILAR_BEHAVIOR = "similar_behavior"
    WRAPS = "wraps"
    PORTS = "ports"
    REIMPLEMENTS = "reimplements"
    DEPENDS_ON = "depends_on"
    REPLACES = "replaces"
    INFORMS = "informs"
    CONFLICTS_WITH = "conflicts_with"


class AdapterMappingItemStatus(str, Enum):
    HYPOTHESIS = "hypothesis"
    CONFIRMED = "confirmed"
    IMPLEMENTED = "implemented"
    REJECTED = "rejected"


class SessionUpdateClassification(str, Enum):
    NO_CHANGE = "no_change"
    CONTINUE_ACTIVE = "continue_active"
    CREATE_CHILD = "create_child"
    CREATE_SIBLING = "create_sibling"
    CREATE_PARENT = "create_parent"
    MERGE_SESSIONS = "merge_sessions"
    SPLIT_SESSION = "split_session"
    SWITCH_ACTIVE = "switch_active"
    QUESTION_ONLY = "question_only"
    MOUNT_SESSION = "mount_session"
    ADAPT_SESSION = "adapt_session"
    UNMOUNT_SESSION = "unmount_session"
    UPDATE_ADAPTER = "update_adapter"


class ActionStakes(str, Enum):
    READ_ONLY = "read_only"
    EXECUTION = "execution"
    MODIFICATION = "modification"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


class ActionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def model_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class PolicyAuthorizationContext(BaseModel):
    allow_private_projection: bool = False
    authorized_by: str | None = None
    reason: str | None = None
    grants: list[str] = Field(default_factory=list)


class SessionPolicy(BaseModel):
    visibility: PolicyVisibility = PolicyVisibility.WORKSPACE
    allow_mount: bool = True
    allow_adapt: bool = True
    allow_outbound_mount: bool = True
    allow_inbound_mount: bool = True
    allow_outbound_adapt: bool = True
    allow_inbound_adapt: bool = True
    inherit_from_parent: bool = True
    allow_policy_override: bool = False
    effective_policy_source_ids: list[str] = Field(default_factory=list)
    license: str | None = None
    security_constraints: list[str] = Field(default_factory=list)


class PolicyCheckEvidence(BaseModel):
    code: str
    ok: bool
    message: str
    source_session_id: str | None = None
    target_session_id: str | None = None


class PolicyEvidence(BaseModel):
    source_effective_policy: SessionPolicy
    target_effective_policy: SessionPolicy
    source_policy_source_ids: list[str] = Field(default_factory=list)
    target_policy_source_ids: list[str] = Field(default_factory=list)
    authorization: PolicyAuthorizationContext | None = None
    checks: list[PolicyCheckEvidence] = Field(default_factory=list)


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
    type: SessionEventType
    session_id: str
    root_session_id: str | None = None
    actor: SessionEventActor = SessionEventActor.SYSTEM
    data: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class AdapterEndpoint(BaseModel):
    session_id: str
    facet: SessionFacetName | None = None
    path: str | None = None
    symbol: str | None = None
    endpoint: str | None = None
    capability: str | None = None
    description: str


class AdapterMapping(BaseModel):
    id: str = Field(default_factory=lambda: model_id("mapping"))
    source: AdapterEndpoint
    target: AdapterEndpoint
    relationship: AdapterRelationship
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    status: AdapterMappingItemStatus = AdapterMappingItemStatus.HYPOTHESIS


class AdapterFacet(BaseModel):
    source_session_id: str
    target_session_id: str
    source_role: AdapterSourceRole
    target_role: AdapterTargetRole
    preservation_mode: PreservationMode
    adaptation_mode: AdaptationMode
    mapping_status: AdapterMappingStatus = AdapterMappingStatus.PROPOSED
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
    projection_source: ProjectionSource = ProjectionSource.HEURISTIC
    relevance_score: float = Field(default=0.5, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    include_selectors: list[ProjectionSelector] = Field(default_factory=list)
    exclude_selectors: list[ProjectionSelector] = Field(default_factory=list)
    budget: ContextProjectionBudget
    rationale: str


class MountSessionRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    user_intent: str
    mount_mode: MountMode
    create_adaptation_session: bool
    make_active: bool = False
    authorization: PolicyAuthorizationContext | None = None


class MountSessionResult(BaseModel):
    mounted_edge: SessionEdge
    adaptation_session: SessionRecord | None = None
    adaptation_edges: list[SessionEdge] = Field(default_factory=list)
    context_projection_delta: ContextProjection
    policy_evidence: PolicyEvidence
    warnings: list[str] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)


class SessionGraphSnapshot(BaseModel):
    sessions: list[SessionRecord] = Field(default_factory=list)
    edges: list[SessionEdge] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)
    projections: list[ContextProjection] = Field(default_factory=list)


class AdapterUpdateProposal(BaseModel):
    adaptation_session_id: str
    new_mappings: list[AdapterMapping] = Field(default_factory=list)
    projection_mode: ProjectionMode | None = None


class SessionUpdateProposal(BaseModel):
    classification: SessionUpdateClassification = SessionUpdateClassification.NO_CHANGE
    active_session_id: str | None = None
    created_sessions: list[SessionRecord] = Field(default_factory=list)
    created_edges: list[SessionEdge] = Field(default_factory=list)
    updated_sessions: list[SessionRecord] = Field(default_factory=list)
    mount_request: MountSessionRequest | None = None
    adapter_update: AdapterUpdateProposal | None = None
    reason: str = "No session graph change proposed."
