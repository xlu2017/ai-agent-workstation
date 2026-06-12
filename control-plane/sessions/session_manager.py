"""Deprecated legacy filesystem session manager.

This module used to create and read ``session.json`` runtime session objects.
Those objects are now deprecated without migration. New code must represent
session identity in the session graph API and must not create new legacy session
metadata.

The public names remain importable so older modules fail with an explicit error
instead of silently creating split-brain session state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SessionError(RuntimeError):
    """Base error for legacy session lifecycle failures."""


class DeprecatedSessionStorageError(SessionError):
    """Raised when code attempts to use deprecated legacy session storage."""


class SessionAlreadyExists(SessionError):
    """Retained only for import compatibility with deprecated callers."""


class SessionNotFound(SessionError):
    """Retained only for import compatibility with deprecated callers."""


@dataclass
class SessionCreateRequest:
    """Deprecated request shape retained only for import compatibility."""

    name: str | None = None
    repo: str | None = None
    branch: str | None = None
    ports: str | None = None
    profile: str | None = None
    task: str | None = None


DEPRECATION_MESSAGE = (
    "Legacy session_manager.py storage is deprecated and intentionally not "
    "migrated. Use /api/session-graph and SessionGraphStore instead."
)


def _raise_deprecated() -> None:
    raise DeprecatedSessionStorageError(DEPRECATION_MESSAGE)


def resolve_repo_path(raw_repo: str | None) -> str:
    """Deprecated. Repo identity belongs in a graph repo session."""

    _raise_deprecated()


def list_sessions() -> list[dict[str, Any]]:
    """Deprecated. Do not read legacy ``session.json`` objects."""

    _raise_deprecated()


def create_session(request: SessionCreateRequest) -> dict[str, Any]:
    """Deprecated. Do not create legacy ``session.json`` objects."""

    _raise_deprecated()


def destroy_session(session_id: str) -> dict[str, Any]:
    """Deprecated. Deletion of legacy objects is intentionally unsupported."""

    _raise_deprecated()


def inspect_session(session_id: str, context_limit: int | None = None) -> dict[str, Any]:
    """Deprecated. Do not inspect legacy ``session.json`` objects."""

    _raise_deprecated()


def get_session_context(session_id: str) -> dict[str, Any]:
    """Deprecated. Context must be read through graph projections/events."""

    _raise_deprecated()
