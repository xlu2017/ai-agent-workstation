"""
Compatibility shim for retired OpenHandsHeadlessExecutor.

All execution now goes through AgenticExecutor.
"""

from execution.agentic_executor import AgenticExecutor

# Backward-compatible alias
OpenHandsHeadlessExecutor = AgenticExecutor

__all__ = ["OpenHandsHeadlessExecutor"]
