from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import MountMode, SessionKind, SessionRecord
from api.services.session_architecture_planner import (
    SessionArchitecturePlan,
    SessionSeed,
    plan_create_child,
    plan_create_root,
    plan_create_sibling,
    plan_move_under,
    plan_question_only,
    propose_context_sources,
)
from api.services.session_graph_service import SessionGraphStore


router = APIRouter(prefix="/api/session-architecture", tags=["session-architecture"])


class RequestContext(BaseModel):
    """Header-backed workspace scope for the preview/apply API.

    This mirrors the session graph API contract: it is not full auth, but it
    prevents the preview/apply scaffold from ignoring workspace ownership once
    the router is mounted.
    """

    workspace_id: str = "default"
    user_id: str | None = None


class SessionSeedRequest(BaseModel):
    kind: SessionKind
    title: str
    summary: str = ""
    facets: dict[str, dict[str, object]] = Field(default_factory=dict)
    state: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_seed(self) -> SessionSeed:
        return SessionSeed(
            kind=self.kind,
            title=self.title,
            summary=self.summary,
            facets=self.facets,
            state=self.state,
            metadata=self.metadata,
        )


class CreateRootPreviewRequest(BaseModel):
    seed: SessionSeedRequest
    reason: str = "Create root session."


class CreateChildPreviewRequest(BaseModel):
    parent_session_id: str
    seed: SessionSeedRequest
    reason: str = "Create child session under active session."


class CreateSiblingPreviewRequest(BaseModel):
    active_session_id: str
    seed: SessionSeedRequest
    reason: str = "Create sibling session in the same root context."


class MoveUnderPreviewRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    user_intent: str
    mount_mode: MountMode = MountMode.REFERENCE
    create_adaptation_session: bool | None = None
    make_active: bool = False


class QuestionOnlyPreviewRequest(BaseModel):
    active_session_id: str
    question: str
    reason: str = "Answer in the active session without changing the graph."


class ContextSourcesPreviewRequest(BaseModel):
    active_session_id: str
    candidate_session_ids: list[str] | None = None
    max_sources: int = 8


def _store() -> SessionGraphStore:
    return SessionGraphStore()


def _context(
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RequestContext:
    return RequestContext(workspace_id=x_workspace_id or "default", user_id=x_user_id)


def _workspace_id(session: SessionRecord) -> str | None:
    value = session.metadata.get("workspace_id")
    return value if isinstance(value, str) else None


def _owner_user_id(session: SessionRecord) -> str | None:
    value = session.metadata.get("owner_user_id")
    return value if isinstance(value, str) else None


def _assert_session_visible(session: SessionRecord, context: RequestContext) -> None:
    workspace_id = _workspace_id(session)
    if workspace_id is not None and workspace_id != context.workspace_id:
        raise HTTPException(403, f"Session {session.id} is outside workspace {context.workspace_id}.")

    if session.policy.visibility == "private":
        owner_user_id = _owner_user_id(session)
        if owner_user_id is not None and owner_user_id != context.user_id:
            raise HTTPException(403, f"Session {session.id} is private.")


def _stamp_session_scope(session: SessionRecord, context: RequestContext) -> SessionRecord:
    session.metadata.setdefault("workspace_id", context.workspace_id)
    if context.user_id:
        session.metadata.setdefault("owner_user_id", context.user_id)
    return session


def _stamp_plan_scope(plan: SessionArchitecturePlan, context: RequestContext) -> SessionArchitecturePlan:
    for session in plan.proposal.created_sessions:
        _stamp_session_scope(session, context)
    return plan


def _get_session(store: SessionGraphStore, session_id: str, context: RequestContext) -> SessionRecord:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _assert_session_visible(session, context)
    return session


def _dump(plan: SessionArchitecturePlan) -> dict[str, object]:
    return {"plan": plan.model_dump(mode="json")}


def _apply_plan(store: SessionGraphStore, plan: SessionArchitecturePlan) -> dict[str, object]:
    try:
        graph = store.apply_update_proposal(plan.proposal)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "plan": plan.model_dump(mode="json"),
        "graph": graph.model_dump(mode="json"),
    }


@router.post("/preview/create-root")
def preview_create_root(
    body: CreateRootPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    plan = plan_create_root(body.seed.to_seed(), reason=body.reason)
    return _dump(_stamp_plan_scope(plan, context))


@router.post("/apply/create-root")
def apply_create_root(
    body: CreateRootPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    plan = _stamp_plan_scope(plan_create_root(body.seed.to_seed(), reason=body.reason), context)
    return _apply_plan(store, plan)


@router.post("/preview/create-child")
def preview_create_child(
    body: CreateChildPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    parent = _get_session(store, body.parent_session_id, context)
    return _dump(_stamp_plan_scope(plan_create_child(parent, body.seed.to_seed(), reason=body.reason), context))


@router.post("/apply/create-child")
def apply_create_child(
    body: CreateChildPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    parent = _get_session(store, body.parent_session_id, context)
    plan = _stamp_plan_scope(plan_create_child(parent, body.seed.to_seed(), reason=body.reason), context)
    return _apply_plan(store, plan)


@router.post("/preview/create-sibling")
def preview_create_sibling(
    body: CreateSiblingPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id, context)
    return _dump(_stamp_plan_scope(plan_create_sibling(active, body.seed.to_seed(), reason=body.reason), context))


@router.post("/apply/create-sibling")
def apply_create_sibling(
    body: CreateSiblingPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id, context)
    plan = _stamp_plan_scope(plan_create_sibling(active, body.seed.to_seed(), reason=body.reason), context)
    return _apply_plan(store, plan)


@router.post("/preview/move-under")
def preview_move_under(
    body: MoveUnderPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    source = _get_session(store, body.source_session_id, context)
    target = _get_session(store, body.target_session_id, context)
    return _dump(plan_move_under(
        source,
        target,
        user_intent=body.user_intent,
        mount_mode=body.mount_mode,
        create_adaptation_session=body.create_adaptation_session,
        make_active=body.make_active,
    ))


@router.post("/apply/move-under")
def apply_move_under(
    body: MoveUnderPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    source = _get_session(store, body.source_session_id, context)
    target = _get_session(store, body.target_session_id, context)
    plan = plan_move_under(
        source,
        target,
        user_intent=body.user_intent,
        mount_mode=body.mount_mode,
        create_adaptation_session=body.create_adaptation_session,
        make_active=body.make_active,
    )
    return _apply_plan(store, plan)


@router.post("/preview/question-only")
def preview_question_only(
    body: QuestionOnlyPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id, context)
    return _dump(plan_question_only(active, question=body.question, reason=body.reason))


@router.post("/apply/question-only")
def apply_question_only(
    body: QuestionOnlyPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id, context)
    plan = plan_question_only(active, question=body.question, reason=body.reason)
    return _apply_plan(store, plan)


@router.post("/preview/context-sources")
def preview_context_sources(
    body: ContextSourcesPreviewRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id, context)
    graph = store.load()
    allowed_ids = set(body.candidate_session_ids or [])
    candidates = []
    for session in graph.sessions:
        if session.id == active.id:
            continue
        if allowed_ids and session.id not in allowed_ids:
            continue
        try:
            _assert_session_visible(session, context)
        except HTTPException:
            continue
        candidates.append(session)
    return {
        "active_session_id": active.id,
        "source_session_ids": propose_context_sources(
            active,
            candidates,
            max_sources=body.max_sources,
        ),
    }
