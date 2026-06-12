from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.multi_frontend import router  # noqa: E402


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SESSION_GRAPH_PATH", str(tmp_path / "session-graph.json"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _payload() -> dict:
    backend = {"label": "API", "base_url": "http://127.0.0.1:8080", "health": "healthy", "port": 8080}
    return {
        "app_title": "Checkout App",
        "intent": "Process web and Android against one backend.",
        "backend": backend,
        "frontends": [
            {
                "label": "Chrome desktop",
                "device_profile": {"label": "Chrome desktop", "os_family": "web", "runtime_kind": "browser", "viewport_width": 1440, "viewport_height": 900},
                "backend_instance_id": "placeholder",
                "target_base_url": backend["base_url"],
                "health": "healthy",
                "current_url": "http://127.0.0.1:8080/checkout",
            },
            {
                "label": "Android emulator",
                "device_profile": {"label": "Pixel", "os_family": "android", "runtime_kind": "emulator", "viewport_width": 412, "viewport_height": 915},
                "backend_instance_id": "placeholder",
                "target_base_url": backend["base_url"],
                "health": "degraded",
                "current_url": "http://10.0.2.2:8080/checkout",
            },
        ],
        "isolation_mode": "shared_backend_separate_user",
    }


def test_multi_frontend_router_creates_matrix_and_trace(monkeypatch, tmp_path: Path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/multi-frontend/topologies", json=_payload())
    assert created.status_code == 200
    topology = created.json()["topology"]
    root_session_id = topology["root_session_id"]
    frontend_id = topology["frontends"][1]["id"]

    matrix = client.get(f"/api/multi-frontend/topologies/{root_session_id}/matrix")
    assert matrix.status_code == 200
    assert matrix.json()["matrix"]["trace_count"] == 0
    assert len(matrix.json()["matrix"]["frontends"]) == 2

    headers = client.get(f"/api/multi-frontend/topologies/{root_session_id}/frontends/{frontend_id}/trace-headers", params={"trace_id": "trace-1", "user_flow_id": "checkout"})
    assert headers.status_code == 200
    assert headers.json()["headers"]["x-agent-frontend-instance-id"] == frontend_id
    assert headers.json()["headers"]["x-agent-trace-id"] == "trace-1"

    trace = client.post("/api/multi-frontend/traces", json={
        "root_session_id": root_session_id,
        "backend_instance_id": topology["backend"]["id"],
        "frontend_instance_id": frontend_id,
        "trace_id": "trace-1",
        "method": "POST",
        "url": "/api/orders",
        "status_code": 500,
        "backend_route": "orders.create",
        "user_flow_id": "checkout",
    })
    assert trace.status_code == 200

    matrix_after = client.get(f"/api/multi-frontend/topologies/{root_session_id}/matrix").json()["matrix"]
    assert matrix_after["trace_count"] == 1
    android = next(row for row in matrix_after["frontends"] if row["frontend_instance_id"] == frontend_id)
    assert android["latest_trace_id"] == "trace-1"
