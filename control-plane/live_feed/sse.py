"""
SSE (Server-Sent Events) endpoint for live session event streaming.

Provides GET /api/sessions/{session_id}/events/stream as an SSE endpoint.
The client receives real-time events as they are appended to the session log.

Transport: SSE (Server-Sent Events) over HTTP. WebSocket upgrade deferred.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from live_feed.events import EventStore, EventType

router = APIRouter()


async def _event_generator(
    store: EventStore,
    session_id: str,
    after_sequence: int = 0,
    poll_interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events as they appear in the event log.

    Polls the JSONL file at `poll_interval` seconds. Sends heartbeat
    comments every 15s to keep the connection alive.
    """
    last_seq = after_sequence
    heartbeat_counter = 0
    max_heartbeats_without_data = 30  # 15 minutes at 30s intervals

    while True:
        events = store.get_events(session_id, after_sequence=last_seq, limit=100)
        if events:
            heartbeat_counter = 0
            for evt in events:
                last_seq = evt.get("sequence", last_seq)
                event_type = evt.get("event_type", "message")
                event_id = evt.get("event_id", "")
                yield f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(evt)}\n\n"
        else:
            heartbeat_counter += 1
            # Send heartbeat comment every ~15s (30 polls at 0.5s)
            if heartbeat_counter % 30 == 0:
                yield f": heartbeat {heartbeat_counter}\n\n"

        await asyncio.sleep(poll_interval)


@router.get("/api/sessions/{session_id}/events/stream")
async def stream_events(
    session_id: str,
    after_sequence: int = Query(0, description="Resume from this sequence number"),
    sessions_dir: str = Query(
        "/opt/workstation/sessions", description="Sessions directory", include_in_schema=False
    ),
) -> StreamingResponse:
    """SSE endpoint for live session event streaming.

    Connect with EventSource:
        const es = new EventSource('/api/sessions/my-session/events/stream');
        es.addEventListener('action_completed', (e) => { ... });

    Events include: user_prompt_received, routing_decision_made, plan_requested,
    plan_generated, plan_started, action_started, action_completed, etc.
    """
    store = EventStore(sessions_dir)
    return StreamingResponse(
        _event_generator(store, session_id, after_sequence),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/sessions/{session_id}/events")
async def get_events(
    session_id: str,
    after_sequence: int = Query(0),
    event_type: str | None = Query(None),
    limit: int = Query(100, le=1000),
    sessions_dir: str = Query(
        "/opt/workstation/sessions", include_in_schema=False
    ),
) -> dict:
    """Get events for a session (non-streaming, paginated)."""
    store = EventStore(sessions_dir)
    type_filter = None
    if event_type:
        try:
            type_filter = [EventType(event_type)]
        except ValueError:
            pass
    events = store.get_events(
        session_id,
        after_sequence=after_sequence,
        event_types=type_filter,
        limit=limit,
    )
    return {"session_id": session_id, "events": events, "count": len(events)}
