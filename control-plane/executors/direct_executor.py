"""
Compatibility module for the retired DirectExecutor.

DirectExecutor used to contain a local LiteLLM structured-tool loop. The platform
now treats OpenHands as the canonical execution runtime. Keep this module only so
legacy imports continue to work; every DirectExecutor call delegates to
OpenHandsExecutorAdapter.
"""

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.openhands_adapter import OpenHandsExecutorAdapter  # noqa: E402


class DirectExecutor(OpenHandsExecutorAdapter):
    """Backward-compatible alias for OpenHandsExecutorAdapter."""


__all__ = ["DirectExecutor"]
