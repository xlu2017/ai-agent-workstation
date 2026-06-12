from __future__ import annotations

from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field

from api.models.session_graph import (
    EdgeType,
    MountMode,
    MountSessionRequest,
    SessionEdge,
    SessionKind,
    SessionRecord,
    SessionStatus,
    SessionUpdateClassification,
    SessionUpdateProposal,
    utc_now,
)


class SessionArchitectureIntent(str, Enum):
    """High-level session-graph changes the controller may request.

    The planner deliberately returns proposals only. It does not execute plans,
    allocate worktrees, call agent-core, mount sessions, or mutate the graph.
    """

    CREATE_ROOT = "create_root"
    CREATE_CHILD = "create_child"
    CREATE_SIBLING = "create_sibling"
    MOVE_UNDER = "move_under"
    MOUNT = "mount"
    ADAPT = "adapt"
    MERGE = "merge"
    FORK = "fork"
    QUESTION_ONLY = "question_only"
    NO_CHANGE = "no_change"


class SessionSeed(BaseModel):
    """Minimal input needed to propose a new session node."""

    kind: SessionKind
    title: str
    summary: str = ""
    facets: dict[str, dict[str, object]] = Field(default_factory=dict)
    state: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class SessionArchitecturePlan(BaseModel):
    """Planner envelope for API/controller integration.

    `proposal` is compatible with SessionGraphStore.apply_update_proposal.
    `mount_request` is carried inside the proposal when the graph change should
    be executed by the session adapter engine.
    """

    intent: SessionArchitectureIntent
    proposal: SessionUpdateProposal
    rationale: str
    warnings: list[str] = Field(default_factory=list)


def _root_for(parent: SessionRecord | None, fallback_id: str) -> str:
    if parent is None:
        return fallback_id
    return parent.root_id or parent.id


def _edge(
    edge_type: EdgeType,
    source_session_id: str,
    target_session_id: str,
    reason: str,
    metadata: dict[str, object] | None = None,
) -> SessionEdge:
    return SessionEdge(
        type=edge_type,
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        metadata={"reason": reason, **(metadata or {})},
    )


def build_session_record(
    seed: SessionSeed,
    *,
    parent: SessionRecord | None = None,
    status: SessionStatus = SessionStatus.PROPOSED,
) -> SessionRecord:
    """Create a session graph record without persisting it."""

    session = SessionRecord(
        kind=seed.kind,
        title=seed.title,
        summary=seed.summary,
        status=status,
        parent_id=parent.id if parent else None,
        facets=seed.facets,
        state=seed.state,
        metadata=seed.metadata,
        updated_at=utc_now(),
    )
    session.root_id = _root_for(parent, session.id)
    return session


def plan_create_root(seed: SessionSeed, *, reason: str = "Create root session.") -> SessionArchitecturePlan:
    session = build_session_record(seed)
    proposal = SessionUpdateProposal(
        classification=SessionUpdateClassification.CREATE_PARENT,
        active_session_id=session.id,
        created_sessions=[session],
        reason=reason,
    )
    return SessionArchitecturePlan(
        intent=SessionArchitectureIntent.CREATE_ROOT,
        proposal=proposal,
        rationale=reason,
    )


def plan_create_child(
    parent: SessionRecord,
    seed: SessionSeed,
    *,
    edge_type: EdgeType = EdgeType.CONTAINS,
    reason: str = "Create child session under active session.",
) -> SessionArchitecturePlan:
    child = build_session_record(seed, parent=parent)
    edge = _edge(edge_type, parent.id, child.id, reason)
    proposal = SessionUpdateProposal(
        classification=SessionUpdateClassification.CREATE_CHILD,
        active_session_id=child.id,
        created_sessions=[child],
        created_edges=[edge],
        reason=reason,
    )
    return SessionArchitecturePlan(
        intent=SessionArchitectureIntent.CREATE_CHILD,
        proposal=proposal,
        rationale=reason,
    )


def plan_create_sibling(
    active: SessionRecord,
    seed: SessionSeed,
    *,
    reason: str = "Create sibling session in the same root context.",
) -> SessionArchitecturePlan:
    sibling = build_session_record(seed)
    sibling.parent_id = active.parent_id
    sibling.root_id = active.root_id or active.id
    edge = _edge(EdgeType.SIBLING_OF, active.id, sibling.id, reason)
    proposal = SessionUpdateProposal(
        classification=SessionUpdateClassification.CREATE_SIBLING,
        active_session_id=sibling.id,
        created_sessions=[sibling],
        created_edges=[edge],
        reason=reason,
    )
    return SessionArchitecturePlan(
        intent=SessionArchitectureIntent.CREATE_SIBLING,
        proposal=proposal,
        rationale=reason,
    )


def adapter_required_for_move(source: SessionRecord, target: SessionRecord, user_intent: str) -> bool:
    """Return true when a move needs a semantic adapter.

    A broad repo/app/container mounted under a focused goal/work/question must be
    projected through an adapter so the source identity and history remain
    intact while only relevant capabilities are exposed to the target context.
    """

    broad_source = source.kind in {SessionKind.REPO, SessionKind.APP, SessionKind.CONTAINER}
    focused_target = target.kind in {SessionKind.GOAL, SessionKind.WORK, SessionKind.QUESTION}
    return source.kind != target.kind or (broad_source and focused_target) or len(user_intent) > 80


def plan_move_under(
    source: SessionRecord,
    target: SessionRecord,
    *,
    user_intent: str,
    mount_mode: MountMode = MountMode.REFERENCE,
    create_adaptation_session: bool | None = None,
    make_active: bool = False,
) -> SessionArchitecturePlan:
    """Propose moving any source session under any target session.

    This is intentionally a semantic mount, not a destructive parent rewrite.
    The source session keeps its own identity, root, events, policy, and facets.
    The adapter engine can then create a projection and optional adapter session.
    """

    needs_adapter = adapter_required_for_move(source, target, user_intent)
    request = MountSessionRequest(
        source_session_id=source.id,
        target_session_id=target.id,
        user_intent=user_intent,
        mount_mode=mount_mode,
        create_adaptation_session=needs_adapter if create_adaptation_session is None else create_adaptation_session,
        make_active=make_active,
    )
    classification = (
        SessionUpdateClassification.ADAPT_SESSION
        if request.create_adaptation_session
        else SessionUpdateClassification.MOUNT_SESSION
    )
    reason = (
        f"Move {source.kind.value} session {source.id} under {target.kind.value} session {target.id} "
        "through a non-destructive semantic mount."
    )
    proposal = SessionUpdateProposal(
        classification=classification,
        active_session_id=target.id if not make_active else source.id,
        mount_request=request,
        reason=reason,
    )
    warnings: list[str] = []
    if needs_adapter:
        warnings.append("Adapter projection required to preserve semantic intent across unlike session kinds.")
    if source.root_id and target.root_id and source.root_id != target.root_id:
        warnings.append("Cross-root mount may require policy authorization if the source is private.")
    return SessionArchitecturePlan(
        intent=SessionArchitectureIntent.MOVE_UNDER,
        proposal=proposal,
        rationale=reason,
        warnings=warnings,
    )


def plan_question_only(
    active: SessionRecord,
    *,
    question: str,
    reason: str = "Answer in the active session without changing the graph.",
) -> SessionArchitecturePlan:
    proposal = SessionUpdateProposal(
        classification=SessionUpdateClassification.QUESTION_ONLY,
        active_session_id=active.id,
        reason=reason,
    )
    return SessionArchitecturePlan(
        intent=SessionArchitectureIntent.QUESTION_ONLY,
        proposal=proposal,
        rationale=question or reason,
    )


def propose_context_sources(
    active: SessionRecord,
    candidates: Iterable[SessionRecord],
    *,
    max_sources: int = 8,
) -> list[str]:
    """Rank candidate sessions that should be considered for context projection.

    The ranking is deterministic scaffold logic. A future LLM/retrieval-backed
    router can replace the scoring while keeping the output contract stable.
    """

    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        if candidate.id == active.id:
            continue
        score = 0
        if candidate.root_id and candidate.root_id == active.root_id:
            score += 40
        if candidate.parent_id and candidate.parent_id == active.parent_id:
            score += 20
        if candidate.kind == active.kind:
            score += 15
        if candidate.kind in {SessionKind.REPO, SessionKind.APP}:
            score += 10
        if candidate.status == SessionStatus.ACTIVE:
            score += 5
        if candidate.title.lower() in active.summary.lower():
            score += 5
        scored.append((score, candidate.id))

    return [session_id for _, session_id in sorted(scored, reverse=True)[:max_sources]]
