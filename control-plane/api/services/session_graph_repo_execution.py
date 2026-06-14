"""Repository attachment execution hooks for session graph work.

Graph chat can create work sessions before a repository is attached. Those work
sessions are truthfully parked as ``blocked_needs_repo``. When a repository later
becomes available on the parent goal, this module re-evaluates those blocked
children through the same execution readiness boundary used by newly-created
work sessions.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from api.models.session_graph import (
    EdgeType,
    SessionEvent,
    SessionEventActor,
    SessionEventType,
    SessionGraphSnapshot,
    SessionKind,
    SessionRecord,
    SessionStatus,
    utc_now,
)
from api.services.session_graph_execution_bridge import (
    build_graph_work_execution_readiness_request,
    execution_readiness_response,
    record_execution_readiness_on_work_session,
    scaffold_execution_readiness_result,
    start_graph_workflow,
    work_facet,
)
from execution.activation import ExecutionActivationService, ExecutionActivationSource


REPO_EXECUTION_METADATA_KEYS = (
    "repo_session_id",
    "repo_id",
    "repo_path",
    "worktree_id",
    "repo_source",
    "clone_url",
    "allowed_actions",
)


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _repo_facet(session: SessionRecord) -> dict[str, Any]:
    facet = session.facets.get("repo", {})
    return facet if isinstance(facet, dict) else {}


def _worktree_id_from_local_path(path_text: str) -> str:
    path = Path(path_text).expanduser()
    worktree_base = Path(os.environ.get("WORKTREE_BASE", os.environ.get("REPOS_DIR", "/opt/workstation/repos"))).expanduser()
    try:
        return str(path.resolve().relative_to(worktree_base.resolve()))
    except (OSError, ValueError):
        return ""


def _repo_session_for(parent_session: SessionRecord, work_session: SessionRecord, graph_sessions: list[SessionRecord]) -> SessionRecord | None:
    repo_session_id = _string(parent_session.metadata.get("repo_session_id")) or _string(work_session.metadata.get("repo_session_id"))
    if not repo_session_id:
        return None
    return next((candidate for candidate in graph_sessions if candidate.id == repo_session_id), None)


def apply_repo_execution_metadata(
    *,
    work_session: SessionRecord,
    parent_session: SessionRecord,
    graph_sessions: list[SessionRecord],
) -> SessionRecord:
    """Copy executable repository metadata from a parent goal onto work.

    The parent goal owns the active repo attachment. Work sessions need a local
    copy because the execution bridge accepts one canonical work-session request.
    """

    metadata_patch: dict[str, object] = {}
    for key in REPO_EXECUTION_METADATA_KEYS:
        value = parent_session.metadata.get(key)
        if value:
            metadata_patch[key] = value

    repo_session = _repo_session_for(parent_session, work_session, graph_sessions)
    if repo_session is not None:
        metadata_patch["repo_session_id"] = repo_session.id
        repo = _repo_facet(repo_session)
        source = _string(repo.get("source"))
        if source == "local":
            repo_path = _string(repo.get("path"))
            worktree_id = _worktree_id_from_local_path(repo_path) if repo_path else ""
            metadata_patch.update(
                {
                    "repo_id": repo_session.id,
                    "repo_path": repo_path,
                    "repo_source": "local",
                }
            )
            if worktree_id:
                metadata_patch["worktree_id"] = worktree_id
        elif source == "github":
            metadata_patch.update(
                {
                    "repo_id": _string(repo.get("full_name")) or repo_session.id,
                    "repo_source": "github",
                    "clone_url": repo.get("clone_url") or "",
                }
            )

    if metadata_patch:
        work_session.metadata = {**work_session.metadata, **metadata_patch}
    return work_session


def execution_context_signature(metadata: dict[str, object]) -> tuple[str, str, str, str]:
    """Return the metadata fields that can unblock graph work execution."""

    return (
        _string(metadata.get("repo_session_id")),
        _string(metadata.get("worktree_id")),
        _string(metadata.get("repo_path")),
        _string(metadata.get("repo_id")),
    )


def execution_context_was_attached(before_metadata: dict[str, object], after_metadata: dict[str, object]) -> bool:
    """Detect a newly available or changed execution context on a goal."""

    before = execution_context_signature(before_metadata)
    after = execution_context_signature(after_metadata)
    return before != after and any(after)


def _is_work_child_of(graph: SessionGraphSnapshot, work_session: SessionRecord, parent_session: SessionRecord) -> bool:
    if work_session.parent_id == parent_session.id:
        return True
    return any(
        edge.type == EdgeType.COMPONENT_OF
        and edge.source_session_id == work_session.id
        and edge.target_session_id == parent_session.id
        for edge in graph.edges
    )


def _is_blocked_needs_repo_work(session: SessionRecord) -> bool:
    facet = work_facet(session)
    execution_state = _string(facet.get("execution_state")) or _string(session.state.get("execution_state"))
    return session.kind == SessionKind.WORK and execution_state == "blocked_needs_repo"


def _mark_ready_for_repo_execution(work_session: SessionRecord) -> SessionRecord:
    facet = dict(work_facet(work_session))
    facet["requires_repo"] = False
    facet["execution_state"] = "ready_for_execution"
    facet["requires_execution_start"] = True
    facet["auto_started"] = False
    work_session.facets = {**work_session.facets, "work": facet}
    work_session.state = {
        **work_session.state,
        "status_reason": "ready_for_execution",
        "execution_state": "ready_for_execution",
        "auto_started": False,
    }
    work_session.status = SessionStatus.ACTIVE
    return work_session


async def reactivate_blocked_work_sessions_after_repo_attach(
    *,
    graph: SessionGraphSnapshot,
    parent_session: SessionRecord,
    source_event_id: str | None = None,
) -> list[dict[str, object]]:
    """Re-evaluate blocked work children after repo context is attached.

    Returns public readiness records for the sessions it touched. The graph is
    mutated in-place and remains unsaved so callers can commit atomically with
    the repo-attach patch.
    """

    if not any(execution_context_signature(parent_session.metadata)):
        return []

    results: list[dict[str, object]] = []
    for index, candidate in enumerate(list(graph.sessions)):
        if not _is_blocked_needs_repo_work(candidate):
            continue
        if not _is_work_child_of(graph, candidate, parent_session):
            continue

        work_session = apply_repo_execution_metadata(
            work_session=candidate,
            parent_session=parent_session,
            graph_sessions=graph.sessions,
        )
        work_session = _mark_ready_for_repo_execution(work_session)
        readiness_request = build_graph_work_execution_readiness_request(
            work_session=work_session,
            parent_session=parent_session,
            source=ExecutionActivationSource.REPO_ATTACHMENT_TRIGGER,
        )
        if readiness_request.worktree_id:
            readiness_result = await ExecutionActivationService(start_workflow=start_graph_workflow).activate(readiness_request)
        else:
            readiness_result = scaffold_execution_readiness_result(readiness_request)

        work_session = record_execution_readiness_on_work_session(work_session, readiness_result)
        work_session.updated_at = utc_now()
        graph.sessions[index] = work_session

        readiness_response = execution_readiness_response(readiness_result)
        execution_started = readiness_response.get("status") == "started" and readiness_response.get("auto_started") is True
        event = SessionEvent(
            type=SessionEventType.WORK_STARTED if execution_started else SessionEventType.WORK_EXECUTION_READINESS_RECORDED,
            session_id=work_session.id,
            root_session_id=work_session.root_id or parent_session.root_id or parent_session.id,
            actor=SessionEventActor.SYSTEM,
            data={
                "parent_session_id": parent_session.id,
                "repo_session_id": work_session.metadata.get("repo_session_id") or parent_session.metadata.get("repo_session_id") or "",
                "worktree_id": readiness_request.worktree_id,
                "execution_state": work_session.state.get("execution_state") or work_facet(work_session).get("execution_state"),
                "auto_started": readiness_response.get("auto_started") is True,
                "execution_readiness": readiness_response,
                "source": ExecutionActivationSource.REPO_ATTACHMENT_TRIGGER.value,
            },
            created_at=utc_now(),
            created_from_event_id=source_event_id,
        )
        graph.events.append(event)
        results.append(
            {
                "session": work_session.model_dump(mode="json"),
                "event": event.model_dump(mode="json"),
                "execution_readiness": readiness_response,
                "auto_started": readiness_response.get("auto_started") is True,
            }
        )

    return results
