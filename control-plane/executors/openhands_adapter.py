"""
Compatibility shim for the retired local executor.

The LLM tool-calling loop and ToolExecutor are now in
execution/agentic_executor.py (AgenticExecutor).

This module re-exports the key symbols for backward compatibility.
"""

from execution.agentic_executor import (  # noqa: F401
    AgenticExecutor,
    ToolExecutor,
    TOOLS,
)

# Legacy alias
OpenHandsExecutorAdapter = AgenticExecutor

__all__ = ["OpenHandsExecutorAdapter", "ToolExecutor", "TOOLS"]
