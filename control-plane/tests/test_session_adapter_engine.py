import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import MountMode, MountSessionRequest, SessionKind, SessionRecord
from api.services.session_adapter_engine import (
    create_adaptation_session,
    generate_context_projection,
    preview_mount_session,
    validate_mount_request,
)
from api.services.session_graph_service import SessionGraphStore


def test_validate_mount_request_requires_adapter_for_cross_kind():
    source = SessionRecord(id="source", kind=SessionKind.REPO, title="Repo")
    target = SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal")
    request = MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference repo under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=False,
    )

    errors = validate_mount_request(source, target, request)

    assert "Adapter session is required" in errors[0]


def test_create_adaptation_session_preserves_source_reference():
    source = SessionRecord(id="openhands", kind=SessionKind.REPO, title="OpenHands")
    target = SessionRecord(id="goal", kind=SessionKind.GOAL, title="Integrate executor behavior")
    request = MountSessionRequest(
        source_session_id="openhands",
        target_session_id="goal",
        user_intent="Map executor capabilities.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    adapter = create_adaptation_session(source, target, request)

    facet = adapter.facets["adapter"]
    assert facet["source_session_id"] == source.id
    assert facet["target_session_id"] == target.id
    assert facet["preservation_mode"] == "lossless_reference"


def test_generate_context_projection_limits_broad_source_for_tiny_goal():
    source = SessionRecord(id="repo", kind=SessionKind.REPO, title="Large Repo")
    target = SessionRecord(id="goal", kind=SessionKind.GOAL, title="Stop looping")
    request = MountSessionRequest(
        source_session_id="repo",
        target_session_id="goal",
        user_intent="Use termination behavior.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    projection = generate_context_projection(source, target, request)

    assert projection.projection_mode.value == "behavior_map"
    assert projection.budget.max_tokens == 4000
    assert "deployment" in projection.exclude_selectors


def test_preview_mount_does_not_persist(tmp_path: Path):
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "graph.json")
    store = SessionGraphStore()
    store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo"))
    store.create_session(SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal"))

    result = preview_mount_session(store, MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference source under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    ))

    assert result.mounted_edge.type.value == "mounted_under"
    assert store.load().edges == []
