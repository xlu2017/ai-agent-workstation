"""
Compatibility module for the OpenHands executor.

Historically this file contained a local parse-and-apply executor despite the
OpenHands name. The platform now treats OpenHands as the canonical execution
runtime through OpenHandsExecutorAdapter.

Keep OpenHandsHeadlessExecutor as an alias so existing imports continue to work.
"""

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))

from executors.openhands_adapter import (  # noqa: E402,F401
    OpenHandsClient,
    OpenHandsExecutorAdapter,
    OpenHandsHTTPError,
)


class OpenHandsHeadlessExecutor(OpenHandsExecutorAdapter):
    """Backward-compatible name for OpenHandsExecutorAdapter."""


__all__ = [
    "OpenHandsClient",
    "OpenHandsExecutorAdapter",
    "OpenHandsHTTPError",
    "OpenHandsHeadlessExecutor",
]
