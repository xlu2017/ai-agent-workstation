import json
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_validate_ambient_source_candidates_marks_existing_contained_path_valid():
    from ambient.event_log import persist_ambient_event, load_ambient_events
    from ambient.source_validation import validate_ambient_source_candidates

    with tempfile.TemporaryDirectory() as tmpdir:
        sessions_dir = Path(tmpdir) / "sessions"
        worktree = Path(tmpdir) / "repos" / "worktree-s1"
        target = worktree / "src" / "components" / "SaveButton.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("export function SaveButton() { return null; }\n")
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "session-meta.json").write_text(json.dumps({"worktree_id": str(worktree)}))
        persist_ambient_event(_browser_selection_event("s1"), sessions_dir=sessions_dir)
        events = load_ambient_events("s1", sessions_dir=sessions_dir)

        result = validate_ambient_source_candidates("s1", events, sessions_dir=sessions_dir)

    assert result["valid_count"] == 1
    assert result["blocked_count"] == 0
    validated = result["validated_candidates"][0]
    assert validated["status"] == "valid"
    assert validated["contained"] is True
    assert validated["exists"] is True
    assert validated["path"] == "src/components/SaveButton.tsx"


def test_validate_source_candidate_blocks_path_traversal():
    from ambient.source_validation import validate_source_candidate

    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_source_candidate({"path": "../outside.py"}, Path(tmpdir))

    assert result["status"] == "blocked"
    assert result["contained"] is False


def test_validated_source_candidates_api_returns_validation_status(monkeypatch):
    from ambient.event_log import persist_ambient_event
    from api import ambient as ambient_api

    with tempfile.TemporaryDirectory() as tmpdir:
        sessions_dir = Path(tmpdir) / "sessions"
        repos_dir = Path(tmpdir) / "repos"
        worktree = repos_dir / "worktree-s1"
        target = worktree / "src" / "components" / "SaveButton.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("export function SaveButton() { return null; }\n")
        session_dir = sessions_dir / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "session-meta.json").write_text(json.dumps({"worktree_id": "worktree-s1"}))
        persist_ambient_event(_browser_selection_event("s1"), sessions_dir=sessions_dir)
        monkeypatch.setattr(ambient_api, "SESSIONS_DIR", sessions_dir)
        monkeypatch.setattr(ambient_api, "REPOS_DIR", repos_dir)

        app = FastAPI()
        app.include_router(ambient_api.router)
        client = TestClient(app)
        response = client.get("/api/sessions/s1/ambient/source-candidates/validated")

    assert response.status_code == 200
    body = response.json()
    assert body["advisory_only"] is True
    assert body["requires_platform_validation"] is True
    assert body["worktree_root"].endswith("worktree-s1")
    assert body["valid_count"] == 1
    assert body["validated_candidates"][0]["status"] == "valid"
    assert body["validated_candidates"][0]["exists"] is True


def _browser_selection_event(session_id: str):
    from ambient.types import AmbientEvent, AmbientSource

    return AmbientEvent(
        event_type="browser.element_selected",
        session_id=session_id,
        source=AmbientSource.BROWSER,
        actor="user",
        confidence=0.91,
        payload={
            "selection": {
                "elements": [
                    {
                        "selector": "[data-testid=save]",
                        "componentName": "SaveButton",
                        "sourceFile": "src/components/SaveButton.tsx",
                        "sourceLine": 12,
                        "sourceConfidence": 0.93,
                    }
                ]
            }
        },
    )
