"""Deprecated session adapter engine.

This module used to own semantic adapter sessions, adapter mappings, and context
projection wiring. The canonical session graph path now uses graph-native mount
actions and starts executable work through the session graph execution bridge.
"""

from __future__ import annotations

from typing import NoReturn


DEPRECATION_MESSAGE = (
    "api.services.session_adapter_engine is deprecated. Use "
    "api.services.session_action_catalog for graph-native mounts and "
    "api.services.session_graph_execution_bridge for executable work sessions."
)


def _deprecated() -> NoReturn:
    raise RuntimeError(DEPRECATION_MESSAGE)


def validate_mount_request(*args, **kwargs):
    _deprecated()


def policy_evidence_for(*args, **kwargs):
    _deprecated()


def generate_default_mappings(*args, **kwargs):
    _deprecated()


def create_adaptation_session(*args, **kwargs):
    _deprecated()


def generate_context_projection(*args, **kwargs):
    _deprecated()


def preview_mount_session(*args, **kwargs):
    _deprecated()


def mount_session(*args, **kwargs):
    _deprecated()


def adapt_session(*args, **kwargs):
    _deprecated()
