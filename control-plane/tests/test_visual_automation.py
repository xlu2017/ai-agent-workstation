"""Tests for visual model provider scaffold."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.server import app  # noqa: E402


def _client():
    return TestClient(app)


def _observation(surface_kind="remote_desktop"):
    return {
        "goal": "Verify the workflow completed and decide the next action.",
        "surface_kind": surface_kind,
        "screenshot": {
            "media_type": "image/png",
            "base64": "",
            "width": 1280,
            "height": 720,
            "source": "test",
        },
        "terminal_output": "pytest passed",
        "verification_criteria": ["success message visible"],
    }


def test_visual_providers_endpoint_lists_expected_providers():
    response = _client().get("/api/visual-automation/providers")

    assert response.status_code == 200
    providers = response.json()["providers"]
    ids = {provider["id"] for provider in providers}
    assert "anthropic_computer_use" in ids
    assert "gemini_computer_use" in ids
    assert "openai_computer_use" in ids
    assert "plain_vision_verifier" in ids


def test_verify_screen_dry_run_selects_plain_verifier_when_configured(monkeypatch):
    monkeypatch.setenv("VISUAL_VERIFIER_API_KEY", "test-credential")

    response = _client().post("/api/visual-automation/verify-screen", json={
        "provider": "auto",
        "dry_run": True,
        "observation": _observation(),
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["provider"] == "plain_vision_verifier"
    assert data["status"] == "uncertain"
    assert data["raw_provider_request"]["content_kinds"] == ["screenshot", "terminal_output"]


def test_propose_action_browser_prefers_gemini_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-credential")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = _client().post("/api/visual-automation/propose-action", json={
        "provider": "auto",
        "dry_run": True,
        "observation": _observation(surface_kind="browser"),
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["provider"] == "gemini_computer_use"
    assert data["action"]["kind"] == "screenshot"


def test_propose_action_desktop_prefers_anthropic_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-credential")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = _client().post("/api/visual-automation/propose-action", json={
        "provider": "auto",
        "dry_run": True,
        "observation": _observation(surface_kind="remote_desktop"),
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["provider"] == "anthropic_computer_use"


def test_anthropic_output_normalizes_to_click_action():
    response = _client().post("/api/visual-automation/normalize-action", json={
        "provider": "anthropic_computer_use",
        "raw_provider_response": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "computer",
                    "id": "toolu_test",
                    "input": {"action": "left_click", "coordinate": [100, 200]},
                }
            ]
        },
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["actions"] == [{
        "kind": "click",
        "x": 100,
        "y": 200,
        "button": "left",
        "text": None,
        "direction": None,
        "amount": None,
        "from_xy": None,
        "to_xy": None,
        "duration_seconds": None,
        "region": None,
    }]


def test_unconfigured_provider_returns_structured_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = _client().post("/api/visual-automation/propose-action", json={
        "provider": "anthropic_computer_use",
        "dry_run": False,
        "observation": _observation(),
    })

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
