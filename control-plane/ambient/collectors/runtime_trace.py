from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource
from ambient.vendor_registry import ensure_vendor_python_path, provider_available

SESSION_HEADER = "x-agent-session-id"
WORKTREE_HEADER = "x-agent-worktree-id"
TRACE_HEADER = "x-agent-trace-id"


def opentelemetry_available() -> bool:
    ensure_vendor_python_path("opentelemetry_python")
    return provider_available("opentelemetry_python", "opentelemetry")


@contextmanager
def ambient_trace_span(name: str, attributes: dict[str, Any] | None = None):
    """Create an OpenTelemetry span when vendored/installed OTel is available.

    This is deliberately a no-op fallback so request observation remains working
    without optional tracing dependencies.
    """

    if not opentelemetry_available():
        yield None
        return
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("jubilant_goggles.ambient")
        with tracer.start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                try:
                    span.set_attribute(key, value)
                except Exception:
                    pass
            yield span
    except Exception:
        yield None


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
        "provider": "opentelemetry" if opentelemetry_available() else "ambient_runtime_timer",
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

    `emit_event` must accept an AmbientEvent. The helper uses vendored/installed
    OpenTelemetry as an implementation detail when available and otherwise emits
    the same ambient event using wall-clock timing.
    """

    started = time.perf_counter()
    with ambient_trace_span("ambient.http_request", {"http.method": request.method, "http.path": str(request.url.path)}):
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
