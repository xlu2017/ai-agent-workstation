"""Ambient context observation fabric.

This package collects structured session context from browser, editor,
terminal, repo, desktop, and runtime sources. Screenshots are treated as a
fallback artifact, not the default observation mechanism.
"""

from ambient.config import AmbientCollectorConfig, get_ambient_config
from ambient.context_packet import build_context_packet
from ambient.event_log import load_ambient_events, persist_ambient_event
from ambient.service import AmbientObservationService
from ambient.types import AmbientEvent, AmbientEventType, AmbientSource, ContextPacket

__all__ = [
    "AmbientCollectorConfig",
    "AmbientEvent",
    "AmbientEventType",
    "AmbientObservationService",
    "AmbientSource",
    "ContextPacket",
    "build_context_packet",
    "get_ambient_config",
    "load_ambient_events",
    "persist_ambient_event",
]
