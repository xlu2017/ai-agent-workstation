"""Compatibility wrapper for the decomposed session graph router.

The session graph API is implemented under ``api.routes.session_graph``.
This module intentionally remains small so legacy imports such as
``from api.session_graph import router`` keep working without preserving the
old monolithic route file.
"""

from __future__ import annotations

from api.routes.session_graph.router import router

__all__ = ["router"]
