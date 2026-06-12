import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402
from api.session_graph import router as legacy_session_graph_router  # noqa: E402
from api.routes.session_graph.router import router as decomposed_session_graph_router  # noqa: E402


def _route_paths() -> list[str]:
    return [getattr(route, "path", "") for route in app.routes]


def test_platform_apps_route_is_registered_once():
    assert _route_paths().count("/api/session-graph/platform-apps") == 1


def test_session_graph_overview_route_is_registered_once():
    assert _route_paths().count("/api/session-graph/overview") == 1


def test_platform_apps_endpoint_returns_applications(monkeypatch):
    monkeypatch.setattr(
        "api.routes.session_graph.platform_apps.discover_popular_applications",
        lambda query="": [{"id": "terminal", "confidence": "installed"}],
    )

    client = TestClient(app)
    response = client.get("/api/session-graph/platform-apps?q=terminal")

    assert response.status_code == 200
    assert response.json() == {"applications": [{"id": "terminal", "confidence": "installed"}]}


def test_legacy_session_graph_import_uses_decomposed_router():
    assert legacy_session_graph_router is decomposed_session_graph_router
