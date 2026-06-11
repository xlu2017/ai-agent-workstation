from __future__ import annotations

from api.models.session_graph import (
    AdaptationMode,
    AdapterEndpoint,
    AdapterFacet,
    AdapterMapping,
    AdapterMappingStatus,
    AdapterRelationship,
    AdapterSourceRole,
    AdapterTargetRole,
    ContextProjection,
    ContextProjectionBudget,
    EdgeType,
    MountMode,
    MountSessionRequest,
    MountSessionResult,
    PolicyCheckEvidence,
    PolicyEvidence,
    PolicyVisibility,
    PreservationMode,
    ProjectionMode,
    ProjectionSelector,
    ProjectionSource,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
    SessionFacetName,
    SessionGraphSnapshot,
    SessionKind,
    SessionPolicy,
    SessionRecord,
)
from api.services.session_graph_service import (
    SessionGraphStore,
    create_session_edge,
    validate_graph_update,
)


def _facet_for_session_kind(kind: SessionKind) -> SessionFacetName | None:
    try:
        return SessionFacetName(kind.value)
    except ValueError:
        return None


def _source_role(source: SessionRecord, mount_mode: MountMode) -> AdapterSourceRole:
    if mount_mode == MountMode.VENDOR:
        return AdapterSourceRole.VENDOR_DEPENDENCY
    if mount_mode == MountMode.COMPARE:
        return AdapterSourceRole.COMPARISON_BASELINE
    if mount_mode == MountMode.TEMPLATE:
        return AdapterSourceRole.DESIGN_PATTERN_SOURCE
    if source.kind == SessionKind.RUNTIME:
        return AdapterSourceRole.RUNTIME_BACKEND
    if source.kind == SessionKind.VALIDATION:
        return AdapterSourceRole.TEST_SOURCE
    if source.kind == SessionKind.REPO:
        return AdapterSourceRole.REFERENCE_IMPLEMENTATION
    return AdapterSourceRole.DOCUMENTATION_SOURCE


def _target_role(target: SessionRecord, mount_mode: MountMode) -> AdapterTargetRole:
    if mount_mode == MountMode.WRAP:
        return AdapterTargetRole.COMPONENT_TO_WRAP
    if mount_mode == MountMode.PORT:
        return AdapterTargetRole.COMPONENT_TO_PORT
    if mount_mode == MountMode.DEPENDENCY:
        return AdapterTargetRole.DEPENDENCY_TO_CALL
    if target.kind == SessionKind.GOAL:
        return AdapterTargetRole.CAPABILITY_TO_INTEGRATE
    if target.kind == SessionKind.APP:
        return AdapterTargetRole.ARCHITECTURE_TO_EMULATE
    return AdapterTargetRole.KNOWLEDGE_SOURCE


def _preservation_mode(mount_mode: MountMode) -> PreservationMode:
    if mount_mode == MountMode.FORK:
        return PreservationMode.FORK
    if mount_mode == MountMode.VENDOR:
        return PreservationMode.VENDOR_IMPORT
    if mount_mode == MountMode.PORT:
        return PreservationMode.PORT
    if mount_mode == MountMode.WRAP:
        return PreservationMode.WRAP
    return PreservationMode.LOSSLESS_REFERENCE


def _adaptation_mode(source: SessionRecord, target: SessionRecord, mount_mode: MountMode) -> AdaptationMode:
    if mount_mode in {MountMode.COMPONENT, MountMode.DEPENDENCY}:
        return AdaptationMode.API_MAPPING
    if mount_mode == MountMode.PORT:
        return AdaptationMode.MIGRATION_PLAN
    if mount_mode == MountMode.WRAP:
        return AdaptationMode.INTERFACE_MAPPING
    if source.kind == SessionKind.REPO and target.kind == SessionKind.GOAL:
        return AdaptationMode.CAPABILITY_MAPPING
    return AdaptationMode.SEMANTIC_PROJECTION


def _adapter_required(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> bool:
    return source.kind != target.kind or request.mount_mode == MountMode.UNKNOWN or len(request.user_intent) > 80


def _effective_policy(session: SessionRecord) -> SessionPolicy:
    policy = session.policy.model_copy(deep=True)
    if session.id not in policy.effective_policy_source_ids:
        policy.effective_policy_source_ids.append(session.id)
    return policy


def _policy_evidence(
    source: SessionRecord,
    target: SessionRecord,
    request: MountSessionRequest,
    errors: list[str],
) -> PolicyEvidence:
    source_policy = _effective_policy(source)
    target_policy = _effective_policy(target)
    checks: list[PolicyCheckEvidence] = []

    def check(code: str, ok: bool, message: str) -> None:
        checks.append(PolicyCheckEvidence(
            code=code,
            ok=ok,
            message=message,
            source_session_id=source.id,
            target_session_id=target.id,
        ))
        if not ok:
            errors.append(message)

    check(
        "source_outbound_mount_allowed",
        source_policy.allow_mount and source_policy.allow_outbound_mount,
        f"Source session {source.id} effective policy does not allow outbound mounting.",
    )
    check(
        "target_inbound_mount_allowed",
        target_policy.allow_mount and target_policy.allow_inbound_mount,
        f"Target session {target.id} effective policy does not allow inbound mounts.",
    )
    if request.create_adaptation_session:
        check(
            "source_outbound_adapt_allowed",
            source_policy.allow_adapt and source_policy.allow_outbound_adapt,
            f"Source session {source.id} effective policy does not allow outbound adaptation.",
        )
        check(
            "target_inbound_adapt_allowed",
            target_policy.allow_adapt and target_policy.allow_inbound_adapt,
            f"Target session {target.id} effective policy does not allow inbound adaptation.",
        )

    private_cross_root = source_policy.visibility == PolicyVisibility.PRIVATE and source.root_id != target.root_id
    check(
        "private_cross_root_projection_authorized",
        not private_cross_root or bool(request.authorization and request.authorization.allow_private_projection),
        "Source effective visibility is private; cross-root projection requires explicit authorization.",
    )

    return PolicyEvidence(
        source_effective_policy=source_policy,
        target_effective_policy=target_policy,
        source_policy_source_ids=source_policy.effective_policy_source_ids,
        target_policy_source_ids=target_policy.effective_policy_source_ids,
        authorization=request.authorization,
        checks=checks,
    )


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
    if source.policy.license:
        warnings.append(f"License constraint should be represented on the adapter: {source.policy.license}.")
    for constraint in source.policy.security_constraints:
        warnings.append(f"Security constraint should be represented on the adapter: {constraint}.")
    return warnings


def validate_mount_request(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> list[str]:
    errors: list[str] = []
    if source.id == target.id:
        errors.append("A session cannot be mounted under itself.")
    _policy_evidence(source, target, request, errors)
    if _adapter_required(source, target, request) and not request.create_adaptation_session:
        errors.append("Adapter session is required for cross-kind, ambiguous, or non-trivial mounts.")
    return errors


def policy_evidence_for(source: SessionRecord, target: SessionRecord, request: MountSessionRequest) -> PolicyEvidence:
    errors: list[str] = []
    evidence = _policy_evidence(source, target, request, errors)
    if errors:
        raise ValueError(" ".join(errors))
    return evidence


def generate_default_mappings(source: SessionRecord, target: SessionRecord, adaptation_mode: AdaptationMode) -> list[AdapterMapping]:
    repo_facet = source.facets.get("repo", {})
    raw_capabilities = repo_facet.get("capabilities", [])
    capabilities = [
        capability for capability in raw_capabilities
        if isinstance(capability, str)
    ] if isinstance(raw_capabilities, list) else []

    if not capabilities:
        known_commands = repo_facet.get("known_commands", {})
        if isinstance(known_commands, dict):
            capabilities.extend(f"{name} command" for name in known_commands.keys())

    from_source = bool(capabilities)
    if not capabilities:
        capabilities = ["session summary", "documented capabilities", "known interfaces", "relevant constraints"]

    return [
        AdapterMapping(
            source=AdapterEndpoint(
                session_id=source.id,
                facet=_facet_for_session_kind(source.kind),
                capability=capability,
                description=f"{source.title}: {capability}",
            ),
            target=AdapterEndpoint(
                session_id=target.id,
                facet=_facet_for_session_kind(target.kind),
                capability=capability,
                description=f"{target.title}: projected {capability}",
            ),
            relationship=AdapterRelationship.PORTS if adaptation_mode == AdaptationMode.MIGRATION_PLAN else AdapterRelationship.INFORMS,
            confidence=0.55 if from_source else 0.35,
            evidence=[
                "source capability mapping" if from_source else "neutral scaffold mapping",
                f"source_session:{source.id}",
                f"target_session:{target.id}",
            ],
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
        mapping_status=AdapterMappingStatus.PROPOSED,
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


def generate_context_projection(
    source: SessionRecord,
    target: SessionRecord,
    request: MountSessionRequest,
    mappings: list[AdapterMapping] | None = None,
) -> ContextProjection:
    broad_source = source.kind in {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER}
    focused_target = target.kind in {SessionKind.GOAL, SessionKind.WORK, SessionKind.QUESTION}
    mapping_based = bool(mappings)
    include_selectors = [ProjectionSelector.ADAPTER_MAPPINGS, ProjectionSelector.CAPABILITIES] if mapping_based else []
    if broad_source and focused_target:
        include_selectors.extend([
            ProjectionSelector.CAPABILITIES,
            ProjectionSelector.BEHAVIORS,
            ProjectionSelector.INTERFACES,
            ProjectionSelector.TERMINATION_CONDITIONS,
        ])
    else:
        include_selectors.extend([ProjectionSelector.SUMMARY, ProjectionSelector.FACETS, ProjectionSelector.RELATIONSHIPS])

    evidence = [f"source:{source.id}:{source.kind.value}", f"target:{target.id}:{target.kind.value}"]
    if mappings:
        evidence.append(f"mapping_count:{len(mappings)}")
        evidence.extend(f"mapping:{mapping.id}:{mapping.relationship.value}:{mapping.confidence}" for mapping in mappings[:8])

    return ContextProjection(
        active_session_id=target.id,
        source_session_ids=[source.id],
        projection_mode=ProjectionMode.BEHAVIOR_MAP if broad_source and focused_target else ProjectionMode.SUMMARY,
        projection_source=ProjectionSource.MAPPING_BASED if mapping_based else ProjectionSource.HEURISTIC,
        relevance_score=0.6 if mapping_based else 0.5,
        evidence=evidence,
        include_selectors=list(dict.fromkeys(include_selectors)),
        exclude_selectors=[
            ProjectionSelector.UNRELATED_UI,
            ProjectionSelector.DEPLOYMENT,
            ProjectionSelector.PLUGINS,
            ProjectionSelector.HISTORICAL_NOISE,
            ProjectionSelector.UNRELATED_CAPABILITIES,
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
    policy_evidence = policy_evidence_for(source, target, request)

    event = SessionEvent(
        type=SessionEventType.SESSION_MOUNTED,
        session_id=target.id,
        root_session_id=target.root_id,
        actor=SessionEventActor.SYSTEM,
        data={
            "source_session_id": source.id,
            "target_session_id": target.id,
            "mount_mode": request.mount_mode.value,
            "preserves_source_identity": True,
            "policy_evidence": policy_evidence.model_dump(mode="json"),
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
    event.data["edge"] = mounted_edge.model_dump(mode="json")

    adaptation_session = create_adaptation_session(source, target, request) if request.create_adaptation_session else None
    adaptation_edges = []
    events = [event]
    mappings: list[AdapterMapping] | None = None
    if adaptation_session:
        adapter_facet = AdapterFacet.model_validate(adaptation_session.facets["adapter"])
        mappings = adapter_facet.mappings
        adapter_event = SessionEvent(
            type=SessionEventType.SESSION_ADAPTER_CREATED,
            session_id=adaptation_session.id,
            root_session_id=adaptation_session.root_id,
            actor=SessionEventActor.SYSTEM,
            data={
                "source_session_id": source.id,
                "target_session_id": target.id,
                "session": adaptation_session.model_dump(mode="json"),
                "facet": adapter_facet.model_dump(mode="json"),
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
    projection = generate_context_projection(source, target, request, mappings)
    events.append(SessionEvent(
        type=SessionEventType.SESSION_ADAPTER_PROJECTION_CREATED,
        session_id=adaptation_session.id if adaptation_session else target.id,
        root_session_id=adaptation_session.root_id if adaptation_session else target.root_id,
        actor=SessionEventActor.SYSTEM,
        data={"projection": projection.model_dump(mode="json")},
    ))
    return MountSessionResult(
        mounted_edge=mounted_edge,
        adaptation_session=adaptation_session,
        adaptation_edges=adaptation_edges,
        context_projection_delta=projection,
        policy_evidence=policy_evidence,
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
    adapted_request = request.model_copy(update={"create_adaptation_session": True})
    errors = validate_mount_request(source, target, adapted_request)
    if errors:
        raise ValueError(" ".join(errors))
    session = create_adaptation_session(source, target, adapted_request)
    adapter_facet = AdapterFacet.model_validate(session.facets["adapter"])
    projection = generate_context_projection(source, target, adapted_request, adapter_facet.mappings)
    event = SessionEvent(
        type=SessionEventType.SESSION_ADAPTER_CREATED,
        session_id=session.id,
        root_session_id=session.root_id,
        actor=SessionEventActor.SYSTEM,
        data={
            "source_session_id": source.id,
            "target_session_id": target.id,
            "session": session.model_dump(mode="json"),
            "facet": adapter_facet.model_dump(mode="json"),
        },
    )
    edges = [
        create_session_edge(EdgeType.ADAPTS_FROM, session.id, source.id, event_id=event.id),
        create_session_edge(EdgeType.ADAPTS_INTO, session.id, target.id, event_id=event.id),
        create_session_edge(
            EdgeType.ADAPTED_UNDER,
            source.id,
            session.id,
            {"target_context_session_id": target.id},
            event.id,
        ),
    ]
    projection_event = SessionEvent(
        type=SessionEventType.SESSION_ADAPTER_PROJECTION_CREATED,
        session_id=session.id,
        root_session_id=session.root_id,
        actor=SessionEventActor.SYSTEM,
        data={"projection": projection.model_dump(mode="json")},
    )
    graph = store.load()
    candidate = SessionGraphSnapshot(
        sessions=[*graph.sessions, session],
        edges=[*graph.edges, *edges],
        events=[*graph.events, event, projection_event],
        projections=[*graph.projections, projection],
    )
    issues = validate_graph_update(candidate)
    if issues:
        raise ValueError(" ".join(issues))
    store.save(candidate)
    return session
