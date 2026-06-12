from __future__ import annotations

from ambient.event_log import summarize_ambient_event
from ambient.reducers import reduce_ambient_events
from ambient.types import AmbientEvent, ContextPacket


def build_context_packet(
    session_id: str,
    events: list[AmbientEvent],
    goal: str | None = None,
    max_recent: int = 20,
) -> ContextPacket:
    """Build a bounded planning packet from ambient events.

    The packet is the object that should be sent into planning/routing. Raw event
    streams stay in storage; the model receives only focused, relevant evidence.
    """

    relevant_events = [event for event in events if event.session_id == session_id]
    state = reduce_ambient_events(relevant_events)
    recent = relevant_events[-max_recent:]
    latest_event = relevant_events[-1] if relevant_events else None

    confidence = 1.0
    if recent:
        confidence = min(event.confidence for event in recent)

    return ContextPacket(
        session_id=session_id,
        goal=goal,
        repo_id=latest_event.repo_id if latest_event else None,
        worktree_id=latest_event.worktree_id if latest_event else None,
        branch=latest_event.branch if latest_event else None,
        ambient_focus=state.current_focus,
        latest=state.latest,
        recent_observations=[summarize_ambient_event(event) for event in recent],
        relevant_files=state.relevant_files,
        evidence_event_ids=[event.event_id for event in recent],
        confidence=confidence,
        privacy=state.privacy,
    )
