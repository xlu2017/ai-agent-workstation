from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_server_mounts_multi_frontend_router(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SESSION_GRAPH_PATH", str(tmp_path / "session-graph.json"))
    if "api.server" in sys.modules:
        server = importlib.reload(sys.modules["api.server"])
    else:
        server = importlib.import_module("api.server")
    client = TestClient(server.app)

    response = client.post("/api/multi-frontend/topologies", json={
        "app_title": "Mounted App",
        "backend": {"label": "API", "base_url": "http://127.0.0.1:8080", "health": "healthy"},
        "frontends": [
            {
                "label": "Chrome desktop",
                "device_profile": {"label": "Chrome desktop", "os_family": "web", "runtime_kind": "browser"},
                "backend_instance_id": "placeholder",
                "target_base_url": "http://127.0.0.1:8080",
                "health": "healthy",
            }
        ],
        "isolation_mode": "shared_backend_separate_user",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["topology"]["backend"]["session_id"]
    assert body["topology"]["frontends"][0]["session_id"]
