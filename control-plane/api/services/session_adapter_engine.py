from __future__ import annotations

from api.models.session_graph import (
    AdapterEndpoint,
    AdapterFacet,
    AdapterMapping,
    ContextProjection,
    ContextProjectionBudget,
    EdgeType,
    MountMode,
    MountSessionRequest,
    MountSessionResult,
    ProjectionMode,
    SessionEvent,
    SessionGraphSnapshot,
    SessionKind,
    SessionRecord,
)
from api.services.session_graph_service import (
    SessionGraphStore,
    append_session_event,
    create_session_edge,
    validate_graph_update,
)


def _source_role(source: SessionRecord, mount_mode: MountMode) -> str:
    if mount_mode == MountMode.VENDOR:
        return "vendor_dependency"
    if mount_mode == MountMode.COMPARE:
        return "comparison_baseline"
    if source.kind == SessionKind.RUNTIME:
        return "runtime_backend"
    if source.kind == SessionKind.REPO:
        return "reference_implementation"
    return "documentation_source"


def _target_role(target: SessionRecord, mount_mode: MountMode) -> str:
    if mount_mode == MountMode.WRAP:
        return "component_to_wrap"
    if mount_mode == MountMode.PORT:
        return "component_to_port"
    if mount_mode == MountMode.DEPENDENCY:
        return "dependency_to_call"
    if target.kind == SessionKind.GOAL:
        return "capability_to_integrate"
    if target.kind == SessionKind.APP:
        return "architecture_to_emulate"
    return "knowledge_source"


def _preservation_mode(mount_mode: MountMode) -> str:
    if mount_mode == MountMode.FORK:
        return "fork"
    if mount_mode == MountMode.VENDOR:
        return "vendor_import"
    if mount_mode == MountMode.PORT:
        return "port"
    if mount_mode == MountMode.WRAP:
        return "wrap"
    return "lossless_reference"


def _adaptation_mode(source: SessionRecord, target: SessionRecord, mount_mode: MountMode) -> str:
    if mount_mode in {MountMode.COMPONENT, MountMode.DEPENDENCY}:
        return "api_mapping"
    if mount_mode == MountMode.PORT:
        return "migration_plan"
    if source.kind == SessionKind.REPO and target.kind == SessionKind.GOAL:
        return "capability_mapping"
    return "semantic_projection"


def _adapter_required(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> bool:
    return source.kind != target.kind or request.mount_mode == MountMode.UNKNOWN or len(request.user_intent) > 80


def _warnings(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> list[str]:
    warnings: list[str] = []
    if source.kind != target.kind:
        warnings.append(f"Cross-kind mount {source.kind.value} to {target.kind.value} needs adapter interpretation.")
    if source.kind in {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER} and target.kind in {
        SessionKind.GOAL,
        SessionKind.WORK,
        SessionKind.QUESTION,
    }:
        warnings.append("Source is much broader than target; semantic projection excludes unrelated context.")
    if request.mount_mode == MountMode.UNKNOWN:
        warnings.append("Mount mode is unknown; mappings should be confirmed before execution use.")
    if source.policy.visibility == "private" and source.root_id != target.root_id:
        warnings.append("Private source visibility requires platform authorization before projection.")
    if source.policy.license:
        warnings.append(f"License constraint should be represented on the adapter: {source.policy.license}.")
    return warnings


def validate_mount_request(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> list[str]:
    errors: list[str] = []
    if source.id == target.id:
        errors.append("A session cannot be mounted under itself.")
    if not source.policy.allow_mount:
        errors.append(f"Source session {source.id} policy does not allow mounting.")
    if request.create_adaptation_session and not source.policy.allow_adapt:
        errors.append(f"Source session {source.id} policy does not allow adaptation.")
    if _adapter_required(source, target, request) and not request.create_adaptation_session:
        errors.append("Adapter session is required for cross-kind, ambiguous, or non-trivial mounts.")
    return errors


def generate_default_mappings(source: SessionRecord, target: SessionRecord, adaptation_mode: str) -> list[AdapterMapping]:
    repo_facet = source.facets.get("repo", {})
    raw_capabilities = repo_facet.get("capabilities", [])
    capabilities = [
        capability for capability in raw_capabilities
        if isinstance(capability, str)
    ] if isinstance(raw_capabilities, list) else []
    if not capabilities:
        capabilities = [
            "shell execution",
            "browser interaction",
            "file editing",
            "agent loop",
            "task completion detection",
            "cancellation handling",
        ]
    return [
        AdapterMapping(
            source=AdapterEndpoint(
                session_id=source.id,
                facet=source.kind.value,
                capability=capability,
                description=f"{source.title}: {capability}",
            ),
            target=AdapterEndpoint(
                session_id=target.id,
                facet=target.kind.value,
                capability=capability,
                description=f"{target.title}: projected {capability}",
            ),
            relationship="ports" if adaptation_mode == "migration_plan" else "informs",
            confidence=0.55,
            evidence=["default scaffold mapping"],
        )
        for capability in capabilities
    ]


def create_adaptation_session(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> SessionRecord:
    adaptation_mode = _adaptation_mode(source, target, request.mount_mode)
    facet = AdapterFacet(
        source_session_id=source.id,
        target_session_id=target.id,
        source_role=_source_role(source, request.mount_mode),
        target_role=_target_role(target, request.mount_mode),
        preservation_mode=_preservation_mode(request.mount_mode),
        adaptation_mode=adaptation_mode,
        mappings=generate_default_mappings(source, target, adaptation_mode),
        constraints=[
            *source.policy.security_constraints,
            *([f"license:{source.policy.license}"] if source.policy.license else []),
        ],
        non_goals=[
            "Do not rewrite source session identity.",
            "Do not collapse source event history.",
        ],
    )
    return SessionRecord(
        kind=SessionKind.ADAPTER,
        title=f"Adapt {source.title} into {target.title}",
        summary=request.user_intent,
        root_id=target.root_id or target.id,
        facets={"adapter": facet.model_dump(mode="json")},
    )


def generate_context_projection(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> ContextProjection:
    broad_source = source.kind in {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER}
    focused_target = target.kind in {SessionKind.GOAL, SessionKind.WORK, SessionKind.QUESTION}
    return ContextProjection(
        active_session_id=source.id if request.make_active else target.id,
        source_session_ids=[source.id],
        projection_mode=ProjectionMode.BEHAVIOR_MAP if broad_source and focused_target else ProjectionMode.SUMMARY,
        include_selectors=[
            "capabilities",
            "behaviors",
            "interfaces",
            "termination_conditions",
        ] if broad_source and focused_target else ["summary", "facets", "relationships"],
        exclude_selectors=[
            "unrelated_ui",
            "deployment",
            "plugins",
            "historical_noise",
        ] if broad_source and focused_target else [],
        budget=ContextProjectionBudget(
            max_tokens=4000 if focused_target else 12000,
            max_files=12 if focused_target else 40,
            max_events=50 if focused_target else 200,
            recency_days=30,
        ),
        rationale=f"Project {source.title} into {target.title} without rewriting source identity.",
    )


def preview_mount_session(store: SessionGraphStore, request: MountSessionRequest) -> MountSessionResult:
    source = store.get_session(request.source_session_id)
    target = store.get_session(request.target_session_id)
    if source is None:
        raise ValueError(f"Source session {request.source_session_id} not found.")
    if target is None:
        raise ValueError(f"Target session {request.target_session_id} not found.")

    errors = validate_mount_request(source, target, request)
    if errors:
        raise ValueError(" ".join(errors))

    event = SessionEvent(
        type="session.mounted",
        session_id=target.id,
        data={
            "source_session_id": source.id,
            "target_session_id": target.id,
            "mount_mode": request.mount_mode.value,
            "preserves_source_identity": True,
        },
    )
    mounted_edge = create_session_edge(
        EdgeType.MOUNTED_UNDER,
        source.id,
        target.id,
        {
            "mount_mode": request.mount_mode.value,
            "user_intent": request.user_intent,
            "preserves_source_identity": True,
        },
        event.id,
    )
    adaptation_session = create_adaptation_session(source, target, request) if request.create_adaptation_session else None
    adaptation_edges = []
    events = [event]
    if adaptation_session:
        adapter_event = SessionEvent(
            type="session.adapter_created",
            session_id=adaptation_session.id,
            data={
                "source_session_id": source.id,
                "target_session_id": target.id,
            },
        )
        events.append(adapter_event)
        adaptation_edges = [
            create_session_edge(EdgeType.ADAPTS_FROM, adaptation_session.id, source.id, event_id=adapter_event.id),
            create_session_edge(EdgeType.ADAPTS_INTO, adaptation_session.id, target.id, event_id=adapter_event.id),
            create_session_edge(
                EdgeType.ADAPTED_UNDER,
                source.id,
                adaptation_session.id,
                {"target_context_session_id": target.id},
                adapter_event.id,
            ),
        ]
    projection = generate_context_projection(source, target, request)
    events.append(SessionEvent(
        type="session.adapter_projection_created",
        session_id=adaptation_session.id if adaptation_session else target.id,
        data={"projection": projection.model_dump(mode="json")},
    ))
    return MountSessionResult(
        mounted_edge=mounted_edge,
        adaptation_session=adaptation_session,
        adaptation_edges=adaptation_edges,
        context_projection_delta=projection,
        warnings=_warnings(source, target, request),
        events=events,
    )


def mount_session(store: SessionGraphStore, request: MountSessionRequest) -> MountSessionResult:
    result = preview_mount_session(store, request)
    graph = store.load()
    candidate = SessionGraphSnapshot(
        sessions=[
            *graph.sessions,
            *([result.adaptation_session] if result.adaptation_session else []),
        ],
        edges=[*graph.edges, result.mounted_edge, *result.adaptation_edges],
        events=[*graph.events, *result.events],
        projections=[*graph.projections, result.context_projection_delta],
    )
    issues = validate_graph_update(candidate)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(candidate)
    return result


def adapt_session(store: SessionGraphStore, request: MountSessionRequest) -> SessionRecord:
    source = store.get_session(request.source_session_id)
    target = store.get_session(request.target_session_id)
    if source is None:
        raise ValueError(f"Source session {request.source_session_id} not found.")
    if target is None:
        raise ValueError(f"Target session {request.target_session_id} not found.")
    session = create_adaptation_session(source, target, request)
    store.create_session(session)
    append_session_event(
        store,
        session.id,
        "session.adapter_created",
        {"source_session_id": source.id, "target_session_id": target.id},
    )
    return session
