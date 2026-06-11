from __future__ import annotations

import json
import os
from pathlib import Path

from api.models.session_graph import (
    ContextProjection,
    EdgeType,
    SessionEdge,
    SessionEvent,
    SessionGraphSnapshot,
    SessionRecord,
    SessionUpdateProposal,
    utc_now,
)


CONTAINMENT_EDGE_TYPES = {
    EdgeType.CONTAINS,
    EdgeType.COMPONENT_OF,
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


class SessionGraphStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_graph_path()

    def load(self) -> SessionGraphSnapshot:
        if not self.path.exists():
            return SessionGraphSnapshot()
        try:
            return SessionGraphSnapshot.model_validate(json.loads(self.path.read_text()))
        except (json.JSONDecodeError, OSError, ValueError):
            return SessionGraphSnapshot()

    def save(self, graph: SessionGraphSnapshot) -> SessionGraphSnapshot:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(graph.model_dump_json(indent=2))
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
        if session.root_id is None:
            session.root_id = session.parent_id or session.id
        graph.sessions.append(session)
        event = SessionEvent(
            type="session.created",
            session_id=session.id,
            data={"session": session.model_dump(mode="json")},
        )
        graph.events.append(event)
        self.save(graph)
        return session

    def list_edges(self, session_id: str | None = None) -> list[SessionEdge]:
        edges = self.load().edges
        if session_id is None:
            return edges
        return [
            edge for edge in edges
            if edge.source_session_id == session_id or edge.target_session_id == session_id
        ]

    def append_edge(self, edge: SessionEdge) -> SessionEdge:
        graph = self.load()
        graph.edges.append(edge)
        self.save(graph)
        return edge

    def append_event(self, event: SessionEvent) -> SessionEvent:
        graph = self.load()
        graph.events.append(event)
        self.save(graph)
        return event

    def append_projection(self, projection: ContextProjection) -> ContextProjection:
        graph = self.load()
        graph.projections.append(projection)
        self.save(graph)
        return projection

    def get_projection_for(self, session_id: str) -> ContextProjection | None:
        projections = self.load().projections
        for projection in reversed(projections):
            if projection.active_session_id == session_id or session_id in projection.source_session_ids:
                return projection
        return None

    def apply_update_proposal(self, proposal: SessionUpdateProposal) -> SessionGraphSnapshot:
        graph = self.load()
        graph.sessions.extend(proposal.created_sessions)
        graph.edges.extend(proposal.created_edges)
        for updated in proposal.updated_sessions:
            graph.sessions = [
                updated if session.id == updated.id else session
                for session in graph.sessions
            ]
        graph.events.append(SessionEvent(
            type="session.updated",
            session_id=proposal.active_session_id or "session-graph",
            data={
                "classification": proposal.classification,
                "reason": proposal.reason,
                "created_session_ids": [session.id for session in proposal.created_sessions],
                "created_edge_ids": [edge.id for edge in proposal.created_edges],
            },
        ))
        issues = validate_graph_update(graph)
        if issues:
            raise ValueError(" ".join(issues))
        self.save(graph)
        return graph


def session_ids(graph: SessionGraphSnapshot) -> set[str]:
    return {session.id for session in graph.sessions}


def reachable(
    edges: list[SessionEdge],
    start_session_id: str,
    target_session_id: str,
) -> bool:
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


def validate_graph_update(graph: SessionGraphSnapshot) -> list[str]:
    issues: list[str] = []
    ids = session_ids(graph)
    for edge in graph.edges:
        if edge.source_session_id not in ids:
            issues.append(f"Edge {edge.id} references missing source {edge.source_session_id}.")
        if edge.target_session_id not in ids:
            issues.append(f"Edge {edge.id} references missing target {edge.target_session_id}.")
        if edge.source_session_id == edge.target_session_id:
            issues.append(f"Edge {edge.id} creates a self-cycle.")
        if edge.type in CONTAINMENT_EDGE_TYPES and reachable(
            graph.edges,
            edge.target_session_id,
            edge.source_session_id,
        ):
            issues.append(f"Edge {edge.id} creates a containment cycle.")
    return issues


def create_session_edge(
    edge_type: EdgeType,
    source_session_id: str,
    target_session_id: str,
    metadata: dict[str, object] | None = None,
    event_id: str | None = None,
) -> SessionEdge:
    return SessionEdge(
        type=edge_type,
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        metadata=metadata or {},
        created_from_event_id=event_id,
    )


def append_session_event(
    store: SessionGraphStore,
    session_id: str,
    event_type: str,
    data: dict[str, object] | None = None,
) -> SessionEvent:
    event = SessionEvent(
        type=event_type,
        session_id=session_id,
        data=data or {},
        created_at=utc_now(),
    )
    return store.append_event(event)
