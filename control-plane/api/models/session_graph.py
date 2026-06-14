from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionKind(str, Enum):
    REPO = "repo"
    APP = "app"
    GOAL = "goal"
    WORK = "work"
    CHAT = "chat"
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
    CHAT = "chat"
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
    WORK_EXECUTION_READINESS_RECORDED = "work.execution_readiness_recorded"
    WORK_STARTED = "work.started"
    WORK_PAUSED = "work.paused"
    WORK_RESUMED = "work.resumed"
    WORK_COMPLETED = "work.completed"
    WORK_CANCELLED = "work.cancelled"
    USER_INTERJECTED = "user.interjected"
    DECISION_RECORDED = "decision.recorded"
    OBSERVATION_RECORDED = "observation.recorded"


class SessionEventActor(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"session-{uuid4().hex[:12]}")
    kind: SessionKind
    title: str
    summary: str = ""
    status: SessionStatus = SessionStatus.PROPOSED
    parent_id: str | None = None
    root_id: str | None = None
    facets: dict[str, object] = Field(default_factory=dict)
    state: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    created_from_event_id: str | None = None


class SessionEdge(BaseModel):
    id: str = Field(default_factory=lambda: f"edge-{uuid4().hex[:12]}")
    type: EdgeType
    source_session_id: str
    target_session_id: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    created_from_event_id: str | None = None


class SessionEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"event-{uuid4().hex[:12]}")
    type: SessionEventType
    session_id: str
    root_session_id: str | None = None
    actor: SessionEventActor
    data: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class ContextProjection(BaseModel):
    id: str = Field(default_factory=lambda: f"projection-{uuid4().hex[:12]}")
    active_session_id: str
    source_session_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    data: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class SessionGraph(BaseModel):
    sessions: list[SessionRecord] = Field(default_factory=list)
    edges: list[SessionEdge] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)
    projections: list[ContextProjection] = Field(default_factory=list)
    version: int = 1


SessionGraphSnapshot = SessionGraph


class SessionUpdateClassification(str, Enum):
    NONE = "none"
    CREATE_SESSION = "create_session"
    UPDATE_SESSION = "update_session"
    CREATE_EDGE = "create_edge"
    MOUNT_SESSION = "mount_session"


class SessionUpdateProposal(BaseModel):
    classification: SessionUpdateClassification = SessionUpdateClassification.NONE
    reason: str = ""
    active_session_id: str | None = None
    created_sessions: list[SessionRecord] = Field(default_factory=list)
    updated_sessions: list[SessionRecord] = Field(default_factory=list)
    created_edges: list[SessionEdge] = Field(default_factory=list)
    mount_request: Any | None = None
