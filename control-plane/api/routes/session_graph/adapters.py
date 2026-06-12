"""Session graph — adapter, mount, unmount routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.models.session_graph import (
    AdapterMapping,
    EdgeType,
    MountSessionRequest,
    SessionEdge,
    SessionKind,
    SessionRecord,
    utc_now,
)
from api.routes.session_graph.helpers import (
    RequestContext,
    _append_event_to_graph,
    _context,
    _get_visible_session,
    _save_or_400,
    _store,
)
from api.services.session_adapter_engine import adapt_session, mount_session, preview_mount_session


router = APIRouter()


class UnmountSessionRequest(BaseModel):
    source_session_id: str
    target_session_id: str
    reason: str = "Unmount session from target context."
    remove_adapter_edges: bool = False


class UpdateAdapterMappingsRequest(BaseModel):
    mode: Literal["replace", "append"] = "replace"
    mappings: list[AdapterMapping] = Field(default_factory=list)
    reason: str = "Update adapter mappings."


@router.post("/mount/preview")
def preview_mount_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        result = preview_mount_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.post("/mount")
def mount_session_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        result = mount_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


@router.post("/unmount")
def unmount_session_endpoint(
    body: UnmountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, object]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    graph = store.load()

    removed_edge_ids: list[str] = []
    retained_edges: list[SessionEdge] = []
    for edge in graph.edges:
        is_mount_edge = (
            edge.type == EdgeType.MOUNTED_UNDER
            and edge.source_session_id == body.source_session_id
            and edge.target_session_id == body.target_session_id
        )
        is_adapter_edge = body.remove_adapter_edges and edge.metadata.get("target_context_session_id") == body.target_session_id
        if is_mount_edge or is_adapter_edge:
            removed_edge_ids.append(edge.id)
        else:
            retained_edges.append(edge)

    if not removed_edge_ids:
        raise HTTPException(404, "No mounted edge found for source and target sessions.")

    graph.edges = retained_edges
    event = _append_event_to_graph(
        graph,
        body.target_session_id,
        "session.unmounted",
        {
            "source_session_id": body.source_session_id,
            "target_session_id": body.target_session_id,
            "removed_edge_ids": removed_edge_ids,
            "reason": body.reason,
            "remove_adapter_edges": body.remove_adapter_edges,
        },
    )
    _save_or_400(store, graph)
    return {"removed_edge_ids": removed_edge_ids, "event": event.model_dump(mode="json")}


@router.post("/adapt")
def adapt_session_endpoint(
    body: MountSessionRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    _get_visible_session(store, body.source_session_id, context)
    _get_visible_session(store, body.target_session_id, context)
    try:
        session = adapt_session(store, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"session": session.model_dump(mode="json")}


@router.put("/adapters/{adapter_session_id}/mappings")
def update_adapter_mappings(
    adapter_session_id: str,
    body: UpdateAdapterMappingsRequest,
    context: RequestContext = Depends(_context),
) -> dict[str, dict[str, object]]:
    store = _store()
    adapter = _get_visible_session(store, adapter_session_id, context)
    if adapter.kind != SessionKind.ADAPTER:
        raise HTTPException(400, f"Session {adapter_session_id} is not an adapter session.")

    graph = store.load()
    updated_session: SessionRecord | None = None
    for session in graph.sessions:
        if session.id != adapter_session_id:
            continue
        adapter_facet = dict(session.facets.get("adapter", {}))
        existing_mappings = adapter_facet.get("mappings", [])
        new_mappings = [mapping.model_dump(mode="json") for mapping in body.mappings]
        adapter_facet["mappings"] = [*existing_mappings, *new_mappings] if body.mode == "append" else new_mappings
        adapter_facet["mapping_status"] = "mapping" if adapter_facet["mappings"] else "proposed"
        session.facets["adapter"] = adapter_facet
        session.updated_at = utc_now()
        updated_session = session
        break

    if updated_session is None:
        raise HTTPException(404, f"Adapter session {adapter_session_id} not found")

    event = _append_event_to_graph(
        graph,
        adapter_session_id,
        "session.adapter_mapping_added",
        {
            "mode": body.mode,
            "mapping_count": len(body.mappings),
            "reason": body.reason,
        },
    )
    store.save(graph)
    return {"session": updated_session.model_dump(mode="json"), "event": event.model_dump(mode="json")}
