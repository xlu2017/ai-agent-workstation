import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import (  # noqa: E402
    EdgeType,
    MountMode,
    MountSessionRequest,
    PolicyVisibility,
    SessionKind,
    SessionPolicy,
    SessionRecord,
)
from api.services.session_adapter_engine import (  # noqa: E402
    create_adaptation_session,
    generate_context_projection,
    mount_session,
    preview_mount_session,
    validate_mount_request,
)
from api.services.session_graph_service import SessionGraphStore  # noqa: E402


def _store(tmp_path: Path) -> SessionGraphStore:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "graph.json")
    return SessionGraphStore()


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

    assert any("Adapter session is required" in error for error in errors)


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
    assert projection.active_session_id == "goal"
    assert projection.budget.max_tokens == 4000
    assert "deployment" in [selector.value for selector in projection.exclude_selectors]


def test_preview_mount_does_not_persist(tmp_path: Path):
    store = _store(tmp_path)
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
    assert result.policy_evidence.source_effective_policy.allow_mount is True
    assert store.load().edges == []


def test_mount_session_persists_adapter_edges_events_and_projection(tmp_path: Path):
    store = _store(tmp_path)
    source = store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo"))
    store.create_session(SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal"))

    result = mount_session(store, MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference source under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    ))

    graph = store.load()
    assert result.adaptation_session is not None
    assert any(session.id == result.adaptation_session.id for session in graph.sessions)
    assert any(edge.type == EdgeType.MOUNTED_UNDER for edge in graph.edges)
    assert any(edge.type == EdgeType.ADAPTS_FROM for edge in graph.edges)
    assert any(event.type.value == "session.mounted" for event in graph.events)
    assert graph.projections

    persisted_source = store.get_session(source.id)
    assert persisted_source is not None
    assert persisted_source.title == source.title
    assert persisted_source.kind == source.kind


def test_target_policy_disallow_blocks_mount():
    source = SessionRecord(id="source", kind=SessionKind.REPO, title="Repo")
    target = SessionRecord(
        id="target",
        kind=SessionKind.GOAL,
        title="Goal",
        policy=SessionPolicy(allow_inbound_mount=False),
    )
    request = MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference source under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    errors = validate_mount_request(source, target, request)

    assert any("does not allow inbound mounts" in error for error in errors)


def test_target_policy_disallow_blocks_adapt():
    source = SessionRecord(id="source", kind=SessionKind.REPO, title="Repo")
    target = SessionRecord(
        id="target",
        kind=SessionKind.GOAL,
        title="Goal",
        policy=SessionPolicy(allow_inbound_adapt=False),
    )
    request = MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference source under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    errors = validate_mount_request(source, target, request)

    assert any("does not allow inbound adaptation" in error for error in errors)


def test_private_cross_root_mount_requires_authorization():
    source = SessionRecord(
        id="source",
        kind=SessionKind.REPO,
        title="Private Repo",
        root_id="root-a",
        policy=SessionPolicy(visibility=PolicyVisibility.PRIVATE),
    )
    target = SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal", root_id="root-b")
    request = MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Reference source under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    errors = validate_mount_request(source, target, request)

    assert any("cross-root projection requires explicit authorization" in error for error in errors)


def test_adapt_session_creates_adapter_edges_and_projection(tmp_path: Path):
    store = _store(tmp_path)
    store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo"))
    store.create_session(SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal"))

    adapter = __import__(
        "api.services.session_adapter_engine",
        fromlist=["adapt_session"],
    ).adapt_session(store, MountSessionRequest(
        source_session_id="source",
        target_session_id="target",
        user_intent="Adapt source behavior under goal.",
        mount_mode=MountMode.REFERENCE,
        create_adaptation_session=True,
    ))

    graph = store.load()
    assert any(session.id == adapter.id for session in graph.sessions)
    assert any(edge.type == EdgeType.ADAPTS_FROM for edge in graph.edges)
    assert any(edge.type == EdgeType.ADAPTS_INTO for edge in graph.edges)
    assert graph.projections


def test_duplicate_session_rejected(tmp_path: Path):
    store = _store(tmp_path)
    store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo"))

    with pytest.raises(ValueError, match="already exists"):
        store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo duplicate"))


def test_duplicate_edge_rejected(tmp_path: Path):
    store = _store(tmp_path)
    store.create_session(SessionRecord(id="source", kind=SessionKind.REPO, title="Repo"))
    store.create_session(SessionRecord(id="target", kind=SessionKind.GOAL, title="Goal"))
    edge = EdgeType.REFERENCES
    from api.services.session_graph_service import create_session_edge

    store.append_edge(create_session_edge(edge, "source", "target"))

    with pytest.raises(ValueError, match="Duplicate edge"):
        store.append_edge(create_session_edge(edge, "source", "target"))


def test_parent_cycle_rejected(tmp_path: Path):
    store = _store(tmp_path)
    store.create_session(SessionRecord(id="a", kind=SessionKind.CONTAINER, title="A"))

    with pytest.raises(ValueError, match="containment cycle"):
        store.create_session(SessionRecord(id="b", kind=SessionKind.CONTAINER, title="B", parent_id="b"))
