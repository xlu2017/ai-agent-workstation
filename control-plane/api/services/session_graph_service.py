from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from pathlib import Path

from api.models.session_graph import (
    ContextProjection,
    EdgeType,
    SessionEdge,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
    SessionGraphSnapshot,
    SessionKind,
    SessionRecord,
    SessionUpdateClassification,
    SessionUpdateProposal,
    utc_now,
)


CONTAINMENT_EDGE_TYPES = {
    EdgeType.CONTAINS,
    EdgeType.MOUNTED_UNDER,
    EdgeType.ADAPTED_UNDER,
    EdgeType.MERGED_INTO,
}


def default_graph_path() -> Path:
    explicit = os.environ.get("SESSION_GRAPH_PATH")
    if explicit:
        return Path(explicit)
    sessions_dir = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
    return sessions_dir / "session-graph.json"


def _test_mode() -> bool:
    return os.environ.get("TEST_MODE", "").lower() in {"1", "true", "yes"}


class SessionGraphStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_graph_path()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def load(self) -> SessionGraphSnapshot:
        if not self.path.exists():
            return SessionGraphSnapshot()
        try:
            return SessionGraphSnapshot.model_validate(json.loads(self.path.read_text()))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            if _test_mode():
                return SessionGraphSnapshot()
            raise RuntimeError(f"Session graph store is corrupt or unreadable at {self.path}: {exc}") from exc

    def save(self, graph: SessionGraphSnapshot) -> SessionGraphSnapshot:
        issues = validate_graph_update(graph)
        if issues:
            raise ValueError(" ".join(issues))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except ImportError:
                pass
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as tmp:
                tmp.write(graph.model_dump_json(indent=2))
                tmp.write("\n")
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, self.path)
        finally:
            try:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except ImportError:
                pass
            os.close(lock_fd)
        return graph

    def list_sessions(self) -> list[SessionRecord]:
        return self.load().sessions

    def get_session(self, session_id: str) -> SessionRecord | None:
        for session in self.load().sessions:
            if session.id == session_id:
                return session
        return None

    def create_session(self, session: SessionRecord) -> SessionRecord:
        graph = self.load()
        if any(existing.id == session.id for existing in graph.sessions):
            raise ValueError(f"Session {session.id} already exists.")
        if session.root_id is None:
            session.root_id = session.parent_id or session.id
        graph.sessions.append(session)
        event = SessionEvent(type=SessionEventType.SESSION_CREATED, session_id=session.id, root_session_id=session.root_id, actor=SessionEventActor.SYSTEM, data={"session": session.model_dump(mode="json")})
        graph.events.append(event)
        self.save(graph)
        return session

    def list_edges(self, session_id: str | None = None) -> list[SessionEdge]:
        edges = self.load().edges
        if session_id is None:
            return edges
        return [edge for edge in edges if edge.source_session_id == session_id or edge.target_session_id == session_id]

    def append_edge(self, edge: SessionEdge) -> SessionEdge:
        graph = self.load()
        if any(existing.id == edge.id for existing in graph.edges):
            raise ValueError(f"Edge {edge.id} already exists.")
        if any(existing.type == edge.type and existing.source_session_id == edge.source_session_id and existing.target_session_id == edge.target_session_id for existing in graph.edges):
            raise ValueError(f"Duplicate edge {edge.type.value} {edge.source_session_id} -> {edge.target_session_id}.")
        graph.edges.append(edge)
        self.save(graph)
        return edge

    def append_event(self, event: SessionEvent) -> SessionEvent:
        graph = self.load()
        if any(existing.id == event.id for existing in graph.events):
            raise ValueError(f"Event {event.id} already exists.")
        graph.events.append(event)
        self.save(graph)
        return event

    def append_projection(self, projection: ContextProjection) -> ContextProjection:
        graph = self.load()
        graph.projections.append(projection)
        self.save(graph)
        return projection

    def get_projection_for(self, session_id: str) -> ContextProjection | None:
        for projection in reversed(self.load().projections):
            if projection.active_session_id == session_id or session_id in projection.source_session_ids:
                return projection
        return None

    def apply_update_proposal(self, proposal: SessionUpdateProposal) -> SessionGraphSnapshot:
        if proposal.mount_request is not None or proposal.classification == SessionUpdateClassification.MOUNT_SESSION:
            if proposal.mount_request is None:
                raise ValueError("mount_session proposal requires mount_request.")
            return _apply_mount_request(self, proposal.mount_request, proposal.reason)

        graph = self.load()
        existing_ids = {session.id for session in graph.sessions}
        for session in proposal.created_sessions:
            if session.id in existing_ids:
                raise ValueError(f"Session {session.id} already exists.")
            existing_ids.add(session.id)
            graph.sessions.append(session)

        existing_edge_keys = {(edge.type, edge.source_session_id, edge.target_session_id) for edge in graph.edges}
        for edge in proposal.created_edges:
            key = (edge.type, edge.source_session_id, edge.target_session_id)
            if key in existing_edge_keys:
                raise ValueError(f"Duplicate edge {edge.type.value} {edge.source_session_id} -> {edge.target_session_id}.")
            existing_edge_keys.add(key)
            graph.edges.append(edge)

        for updated in proposal.updated_sessions:
            if updated.id not in existing_ids:
                raise ValueError(f"Cannot update missing session {updated.id}.")
            graph.sessions = [updated if session.id == updated.id else session for session in graph.sessions]

        graph.events.append(SessionEvent(type=SessionEventType.SESSION_UPDATED, session_id=proposal.active_session_id or "session-graph", root_session_id=proposal.active_session_id, actor=SessionEventActor.SYSTEM, data={"classification": proposal.classification.value, "reason": proposal.reason, "created_session_ids": [session.id for session in proposal.created_sessions], "created_edge_ids": [edge.id for edge in proposal.created_edges]}))
        self.save(graph)
        return graph


def _mount_field(mount_request: object, key: str, default: object = "") -> object:
    value = mount_request.get(key, default) if isinstance(mount_request, dict) else getattr(mount_request, key, default)
    if isinstance(value, Enum):
        return value.value
    return value


def _apply_mount_request(store: SessionGraphStore, mount_request: object, reason: str) -> SessionGraphSnapshot:
    graph = store.load()
    source_id = str(_mount_field(mount_request, "source_session_id"))
    target_id = str(_mount_field(mount_request, "target_session_id"))
    if not source_id or not target_id:
        raise ValueError("mount_request requires source_session_id and target_session_id.")
    if source_id == target_id:
        raise ValueError("A session cannot be mounted under itself.")
    source = next((session for session in graph.sessions if session.id == source_id), None)
    target_index = next((idx for idx, session in enumerate(graph.sessions) if session.id == target_id), None)
    if source is None:
        raise ValueError(f"Source session {source_id} not found.")
    if target_index is None:
        raise ValueError(f"Target session {target_id} not found.")
    if any(edge.type == EdgeType.MOUNTED_UNDER and edge.source_session_id == source_id and edge.target_session_id == target_id for edge in graph.edges):
        raise ValueError(f"Duplicate mounted_under edge {source_id} -> {target_id}.")
    edge = SessionEdge(type=EdgeType.MOUNTED_UNDER, source_session_id=source_id, target_session_id=target_id, metadata={"reason": reason or str(_mount_field(mount_request, "user_intent", "Mount session.")), "mount_mode": str(_mount_field(mount_request, "mount_mode", "reference")), "source": "session_graph_service"})
    graph.edges.append(edge)
    if bool(_mount_field(mount_request, "make_active", False)):
        target = graph.sessions[target_index]
        metadata = dict(target.metadata)
        metadata["active_context_session_id"] = source_id
        if source.kind == SessionKind.REPO:
            metadata["repo_session_id"] = source_id
            repo_facet = source.facets.get("repo", {})
            if isinstance(repo_facet, dict):
                if isinstance(repo_facet.get("path"), str):
                    metadata["repo_path"] = repo_facet["path"]
                if isinstance(repo_facet.get("full_name"), str):
                    metadata["repo_id"] = repo_facet["full_name"]
        target.metadata = metadata
        graph.sessions[target_index] = target
    graph.events.append(SessionEvent(type=SessionEventType.SESSION_MOUNTED, session_id=target_id, actor=SessionEventActor.SYSTEM, data={"source_session_id": source_id, "target_session_id": target_id, "edge_id": edge.id}))
    store.save(graph)
    return graph


def session_ids(graph: SessionGraphSnapshot) -> set[str]:
    return {session.id for session in graph.sessions}


def reachable(edges: list[SessionEdge], start_session_id: str, target_session_id: str) -> bool:
    visited: set[str] = set()
    stack = [start_session_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        if current == target_session_id:
            return True
        visited.add(current)
        for edge in edges:
            if edge.type in CONTAINMENT_EDGE_TYPES and edge.source_session_id == current:
                stack.append(edge.target_session_id)
    return False


def _parent_edges(graph: SessionGraphSnapshot) -> list[SessionEdge]:
    explicit_contains = {(edge.source_session_id, edge.target_session_id) for edge in graph.edges if edge.type == EdgeType.CONTAINS}
    parent_edges: list[SessionEdge] = []
    for session in graph.sessions:
        if session.parent_id is None:
            continue
        if (session.parent_id, session.id) in explicit_contains:
            continue
        parent_edges.append(SessionEdge(type=EdgeType.CONTAINS, source_session_id=session.parent_id, target_session_id=session.id, metadata={"derived_from": "parent_id"}))
    return parent_edges


def validate_graph_update(graph: SessionGraphSnapshot) -> list[str]:
    issues: list[str] = []
    ids = session_ids(graph)
    duplicate_session_ids = {session.id for session in graph.sessions if sum(1 for candidate in graph.sessions if candidate.id == session.id) > 1}
    for session_id in sorted(duplicate_session_ids):
        issues.append(f"Duplicate session id {session_id}.")
    for session in graph.sessions:
        if session.parent_id is not None and session.parent_id not in ids:
            issues.append(f"Session {session.id} references missing parent {session.parent_id}.")
    all_edges = [*graph.edges, *_parent_edges(graph)]
    seen_edge_keys: set[tuple[EdgeType, str, str]] = set()
    for edge in all_edges:
        key = (edge.type, edge.source_session_id, edge.target_session_id)
        if key in seen_edge_keys:
            issues.append(f"Duplicate edge {edge.type.value} {edge.source_session_id} -> {edge.target_session_id}.")
        seen_edge_keys.add(key)
        if edge.source_session_id not in ids:
            issues.append(f"Edge {edge.id} references missing source {edge.source_session_id}.")
        if edge.target_session_id not in ids:
            issues.append(f"Edge {edge.id} references missing target {edge.target_session_id}.")
        if edge.source_session_id == edge.target_session_id:
            issues.append(f"Edge {edge.id} creates a self-cycle.")
        if edge.type in CONTAINMENT_EDGE_TYPES and reachable(all_edges, edge.target_session_id, edge.source_session_id):
            issues.append(f"Edge {edge.id} creates a containment cycle.")
    return issues


def create_session_edge(edge_type: EdgeType, source_session_id: str, target_session_id: str, metadata: dict[str, object] | None = None, event_id: str | None = None) -> SessionEdge:
    return SessionEdge(type=edge_type, source_session_id=source_session_id, target_session_id=target_session_id, metadata=metadata or {}, created_from_event_id=event_id)


def append_session_event(store: SessionGraphStore, session_id: str, event_type: SessionEventType, data: dict[str, object] | None = None, root_session_id: str | None = None, actor: SessionEventActor = SessionEventActor.SYSTEM) -> SessionEvent:
    event = SessionEvent(type=event_type, session_id=session_id, root_session_id=root_session_id, actor=actor, data=data or {}, created_at=utc_now())
    return store.append_event(event)
