import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app


def _client():
    return TestClient(app)


def test_services_include_safe_action_flags():
    response = _client().get("/api/services")

    assert response.status_code == 200
    services = {service["name"]: service for service in response.json()["services"]}
    assert services["dashboard"]["can_restart"] is True
    assert services["control-plane"]["can_restart"] is True
    assert services["control-plane"]["can_stop"] is False


def test_control_plane_stop_is_disabled():
    response = _client().post("/api/services/control-plane/stop")

    assert response.status_code == 200
    data = response.json()
    assert data["stopped"] is False
    assert "disabled" in data["error"]
