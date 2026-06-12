from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import MountMode, SessionKind
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


def _get_session(store: SessionGraphStore, session_id: str):
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    return session


def _dump(plan: SessionArchitecturePlan) -> dict[str, object]:
    return {"plan": plan.model_dump(mode="json")}


@router.post("/preview/create-root")
def preview_create_root(body: CreateRootPreviewRequest) -> dict[str, object]:
    return _dump(plan_create_root(body.seed.to_seed(), reason=body.reason))


@router.post("/preview/create-child")
def preview_create_child(body: CreateChildPreviewRequest) -> dict[str, object]:
    store = _store()
    parent = _get_session(store, body.parent_session_id)
    return _dump(plan_create_child(parent, body.seed.to_seed(), reason=body.reason))


@router.post("/preview/create-sibling")
def preview_create_sibling(body: CreateSiblingPreviewRequest) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id)
    return _dump(plan_create_sibling(active, body.seed.to_seed(), reason=body.reason))


@router.post("/preview/move-under")
def preview_move_under(body: MoveUnderPreviewRequest) -> dict[str, object]:
    store = _store()
    source = _get_session(store, body.source_session_id)
    target = _get_session(store, body.target_session_id)
    return _dump(plan_move_under(
        source,
        target,
        user_intent=body.user_intent,
        mount_mode=body.mount_mode,
        create_adaptation_session=body.create_adaptation_session,
        make_active=body.make_active,
    ))


@router.post("/preview/question-only")
def preview_question_only(body: QuestionOnlyPreviewRequest) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id)
    return _dump(plan_question_only(active, question=body.question, reason=body.reason))


@router.post("/preview/context-sources")
def preview_context_sources(body: ContextSourcesPreviewRequest) -> dict[str, object]:
    store = _store()
    active = _get_session(store, body.active_session_id)
    graph = store.load()
    allowed_ids = set(body.candidate_session_ids or [])
    candidates = [
        session for session in graph.sessions
        if session.id != active.id and (not allowed_ids or session.id in allowed_ids)
    ]
    return {
        "active_session_id": active.id,
        "source_session_ids": propose_context_sources(
            active,
            candidates,
            max_sources=body.max_sources,
        ),
    }
