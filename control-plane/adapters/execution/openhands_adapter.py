"""
Compatibility shim — redirects to AgenticExecutor.

The platform now uses AgenticExecutor as the primary coding execution backend.
This module exists only for backward compatibility of imports.
"""

from execution.agentic_executor import AgenticExecutor

# Backward-compatible alias
OpenHandsExecutorAdapter = AgenticExecutor

__all__ = ["OpenHandsExecutorAdapter"]
