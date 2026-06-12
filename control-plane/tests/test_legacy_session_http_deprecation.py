import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes.sessions import router as legacy_router  # noqa: E402
from api.routes.session_events import router as legacy_events_router  # noqa: E402


def client() -> TestClient:
    app = FastAPI()
    app.include_router(legacy_router)
    app.include_router(legacy_events_router)
    return TestClient(app)


def test_legacy_session_collection_is_gone():
    response = client().get("/api/sessions")
    assert response.status_code == 410
    assert response.json()["detail"]["migration"] == "not_supported"


def test_legacy_session_member_is_gone():
    response = client().get("/api/sessions/example/context")
    assert response.status_code == 410
    assert response.json()["detail"]["replacement"] == "/api/session-graph"


def test_legacy_v2_timeline_is_gone():
    response = client().get("/api/v2/sessions/example/timeline")
    assert response.status_code == 410
    assert response.json()["detail"]["replacement"] == "/api/session-graph/events"
