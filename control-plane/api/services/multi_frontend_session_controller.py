from __future__ import annotations

from api.models.multi_frontend import (
    CrossClientTrace,
    CreateMultiFrontendTopologyRequest,
    FrontendMatrixRow,
    MultiFrontendMatrix,
    MultiFrontendTopology,
    RegisterCrossClientTraceRequest,
    TraceCorrelationHeaders,
)
from api.models.session_graph import (
    EdgeType,
    SessionEdge,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
    SessionKind,
    SessionRecord,
    SessionStatus,
    utc_now,
)
from api.services.session_graph_service import SessionGraphStore


class MultiFrontendSessionController:
    """Coordinates one backend session with many isolated frontend client sessions.

    Intent:
    - keep frontend browser/emulator state isolated;
    - keep backend traces/logs shared and correlated;
    - represent the topology in the existing session graph;
    - avoid flattening all clients into one ambiguous browser session.
    """

    def __init__(self, store: SessionGraphStore | None = None):
        self.store = store or SessionGraphStore()

    def create_topology(self, request: CreateMultiFrontendTopologyRequest) -> MultiFrontendTopology:
        graph = self.store.load()
        root_session = SessionRecord(
            kind=SessionKind.APP,
            title=request.app_title,
            summary=request.intent,
            status=SessionStatus.ACTIVE,
            facets={
                "app": {
                    "intent": request.intent,
                    "multi_frontend": True,
                    "isolation_mode": request.isolation_mode.value,
                }
            },
            metadata={**request.metadata, "created_by": "multi_frontend_session_controller"},
        )
        root_session.root_id = root_session.id

        backend = request.backend.model_copy(deep=True)
        backend_session = SessionRecord(
            kind=SessionKind.RUNTIME,
            title=f"Backend: {backend.label}",
            summary="Shared backend instance for multi-frontend processing.",
            status=SessionStatus.ACTIVE,
            parent_id=root_session.id,
            root_id=root_session.id,
            facets={
                "runtime": {
                    "role": "backend",
                    "backend_instance": backend.model_dump(mode="json"),
                }
            },
            state={"health": backend.health.value, "base_url": backend.base_url},
            metadata={"multi_frontend_role": "backend"},
        )
        backend.session_id = backend_session.id
        backend_session.facets["runtime"]["backend_instance"] = backend.model_dump(mode="json")

        frontend_sessions: list[SessionRecord] = []
        frontends = []
        for frontend in request.frontends:
            copied = frontend.model_copy(deep=True)
            copied.backend_instance_id = backend.id
            session = SessionRecord(
                kind=SessionKind.RUNTIME,
                title=f"Frontend: {copied.label}",
                summary="Isolated frontend client connected to the shared backend.",
                status=SessionStatus.ACTIVE,
                parent_id=root_session.id,
                root_id=root_session.id,
                facets={
                    "runtime": {
                        "role": "frontend_client",
                        "frontend_instance": copied.model_dump(mode="json"),
                    }
                },
                state={
                    "health": copied.health.value,
                    "current_url": copied.current_url,
                    "target_base_url": copied.target_base_url,
                },
                metadata={
                    "multi_frontend_role": "frontend",
                    "backend_instance_id": backend.id,
                    "device_profile_id": copied.device_profile.id,
                },
            )
            copied.session_id = session.id
            session.facets["runtime"]["frontend_instance"] = copied.model_dump(mode="json")
            frontend_sessions.append(session)
            frontends.append(copied)

        graph.sessions.extend([root_session, backend_session, *frontend_sessions])
        graph.edges.append(SessionEdge(
            type=EdgeType.CONTAINS,
            source_session_id=root_session.id,
            target_session_id=backend_session.id,
            metadata={"relationship": "app_has_shared_backend"},
        ))
        for session in frontend_sessions:
            graph.edges.append(SessionEdge(
                type=EdgeType.CONTAINS,
                source_session_id=root_session.id,
                target_session_id=session.id,
                metadata={"relationship": "app_has_frontend_client"},
            ))
            graph.edges.append(SessionEdge(
                type=EdgeType.DEPENDS_ON,
                source_session_id=session.id,
                target_session_id=backend_session.id,
                metadata={"relationship": "frontend_uses_shared_backend"},
            ))

        topology = MultiFrontendTopology(
            root_session_id=root_session.id,
            backend=backend,
            frontends=frontends,
            isolation_mode=request.isolation_mode,
        )
        root_session.state["multi_frontend_topology"] = topology.model_dump(mode="json")
        root_session.updated_at = utc_now()
        graph.events.append(SessionEvent(
            type=SessionEventType.SESSION_CREATED,
            session_id=root_session.id,
            root_session_id=root_session.id,
            actor=SessionEventActor.SYSTEM,
            data={
                "kind": "multi_frontend_topology_created",
                "backend_session_id": backend_session.id,
                "frontend_session_ids": [session.id for session in frontend_sessions],
                "isolation_mode": request.isolation_mode.value,
            },
        ))
        self.store.save(graph)
        return topology

    def get_topology(self, root_session_id: str) -> MultiFrontendTopology:
        root = self.store.get_session(root_session_id)
        if root is None:
            raise ValueError(f"Root session {root_session_id} not found")
        payload = root.state.get("multi_frontend_topology")
        if not isinstance(payload, dict):
            raise ValueError(f"Session {root_session_id} is not a multi-frontend topology")
        return MultiFrontendTopology.model_validate(payload)

    def build_trace_headers(
        self,
        root_session_id: str,
        frontend_instance_id: str,
        user_flow_id: str | None = None,
        trace_id: str | None = None,
    ) -> TraceCorrelationHeaders:
        topology = self.get_topology(root_session_id)
        frontend = next((item for item in topology.frontends if item.id == frontend_instance_id), None)
        if frontend is None:
            raise ValueError(f"Frontend instance {frontend_instance_id} not found")
        if not topology.backend.session_id or not frontend.session_id:
            raise ValueError("Topology is missing session ids")
        return TraceCorrelationHeaders(
            root_session_id=root_session_id,
            backend_session_id=topology.backend.session_id,
            frontend_session_id=frontend.session_id,
            frontend_instance_id=frontend.id,
            device_profile_id=frontend.device_profile.id,
            user_flow_id=user_flow_id,
            trace_id=trace_id,
        )

    def register_trace(self, request: RegisterCrossClientTraceRequest) -> CrossClientTrace:
        graph = self.store.load()
        root_index = next((idx for idx, session in enumerate(graph.sessions) if session.id == request.root_session_id), None)
        if root_index is None:
            raise ValueError(f"Root session {request.root_session_id} not found")
        root = graph.sessions[root_index]
        topology_payload = root.state.get("multi_frontend_topology")
        if not isinstance(topology_payload, dict):
            raise ValueError(f"Session {request.root_session_id} is not a multi-frontend topology")
        topology = MultiFrontendTopology.model_validate(topology_payload)
        trace = CrossClientTrace(**request.model_dump())
        topology.traces.append(trace)
        for frontend in topology.frontends:
            if frontend.id == request.frontend_instance_id:
                frontend.latest_trace_id = request.trace_id
        topology.updated_at = utc_now()
        root.state["multi_frontend_topology"] = topology.model_dump(mode="json")
        root.updated_at = utc_now()
        graph.sessions[root_index] = root
        graph.events.append(SessionEvent(
            type=SessionEventType.OBSERVATION_RECORDED,
            session_id=request.root_session_id,
            root_session_id=request.root_session_id,
            actor=SessionEventActor.SYSTEM,
            data={"kind": "cross_client_trace_registered", "trace": trace.model_dump(mode="json")},
        ))
        self.store.save(graph)
        return trace

    def matrix(self, root_session_id: str) -> MultiFrontendMatrix:
        topology = self.get_topology(root_session_id)
        rows = [
            FrontendMatrixRow(
                frontend_instance_id=frontend.id,
                frontend_session_id=frontend.session_id,
                label=frontend.label,
                os_family=frontend.device_profile.os_family,
                runtime_kind=frontend.device_profile.runtime_kind,
                health=frontend.health,
                current_url=frontend.current_url,
                latest_trace_id=frontend.latest_trace_id,
                auth_identity=frontend.auth_identity,
                tenant_id=frontend.tenant_id,
            )
            for frontend in topology.frontends
        ]
        return MultiFrontendMatrix(
            root_session_id=root_session_id,
            backend_session_id=topology.backend.session_id,
            backend_label=topology.backend.label,
            backend_base_url=topology.backend.base_url,
            backend_health=topology.backend.health,
            isolation_mode=topology.isolation_mode,
            frontends=rows,
            trace_count=len(topology.traces),
            updated_at=topology.updated_at,
        )
