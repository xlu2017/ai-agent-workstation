from __future__ import annotations

import time
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource

SESSION_HEADER = "x-agent-session-id"
WORKTREE_HEADER = "x-agent-worktree-id"
TRACE_HEADER = "x-agent-trace-id"


def build_runtime_request_event(
    session_id: str,
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    trace_id: str | None = None,
    route: str | None = None,
    handler: str | None = None,
    repo_id: str | None = None,
    worktree_id: str | None = None,
    branch: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AmbientEvent:
    payload = {
        "method": method,
        "path": path,
        "route": route,
        "handler": handler,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "trace_id": trace_id,
    }
    if extra:
        payload.update(extra)
    return AmbientEvent(
        event_type=AmbientEventType.RUNTIME_REQUEST_OBSERVED.value,
        session_id=session_id,
        source=AmbientSource.RUNTIME_TRACE,
        repo_id=repo_id,
        worktree_id=worktree_id,
        branch=branch,
        confidence=0.95,
        payload=payload,
    )


async def ambient_fastapi_middleware(request, call_next, emit_event):
    """FastAPI middleware helper for runtime request observation.

    Usage in an app that wants to emit ambient events:

    ```python
    @app.middleware("http")
    async def ambient_runtime(request, call_next):
        return await ambient_fastapi_middleware(request, call_next, emit_event)
    ```

    `emit_event` must accept an AmbientEvent. This helper intentionally does not
    import FastAPI or OpenTelemetry so it remains testable without optional deps.
    """

    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)

    session_id = request.headers.get(SESSION_HEADER)
    if session_id:
        scope = getattr(request, "scope", {}) or {}
        route = scope.get("path") if isinstance(scope, dict) else None
        event = build_runtime_request_event(
            session_id=session_id,
            method=request.method,
            path=str(request.url.path),
            status_code=getattr(response, "status_code", 0),
            duration_ms=duration_ms,
            trace_id=request.headers.get(TRACE_HEADER),
            worktree_id=request.headers.get(WORKTREE_HEADER),
            route=route,
        )
        emit_event(event)
    return response
