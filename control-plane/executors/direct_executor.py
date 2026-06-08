"""
Compatibility shim for the retired DirectExecutor.

All execution now goes through AgenticExecutor.
"""

from execution.agentic_executor import AgenticExecutor


class DirectExecutor(AgenticExecutor):
    """Backward-compatible alias for AgenticExecutor."""


__all__ = ["DirectExecutor"]
