"""
Compatibility shim — redirects to DeterministicExecutor.

The platform now uses DeterministicExecutor as the simple/fallback execution backend.
This module exists only for backward compatibility of imports.
"""

from execution.deterministic_executor import DeterministicExecutor

# Backward-compatible alias
FallbackExecutorAdapter = DeterministicExecutor

__all__ = ["FallbackExecutorAdapter"]
