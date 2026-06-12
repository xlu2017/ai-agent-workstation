import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import (  # noqa: E402
    EdgeType,
    MountMode,
    SessionKind,
    SessionRecord,
    SessionUpdateClassification,
)
from api.services.session_architecture_planner import (  # noqa: E402
    SessionArchitectureIntent,
    SessionSeed,
    adapter_required_for_move,
    build_session_record,
    plan_create_child,
    plan_create_root,
    plan_create_sibling,
    plan_move_under,
    plan_question_only,
    propose_context_sources,
)


def test_build_session_record_sets_root_to_self_for_root_session():
    record = build_session_record(SessionSeed(kind=SessionKind.REPO, title="Frontend repo"))

    assert record.root_id == record.id
    assert record.parent_id is None
    assert record.kind == SessionKind.REPO


def test_plan_create_child_inherits_parent_root_and_contains_edge():
    parent = SessionRecord(id="app", kind=SessionKind.APP, title="Application", root_id="root")

    plan = plan_create_child(parent, SessionSeed(kind=SessionKind.WORK, title="Fix auth bug"))

    child = plan.proposal.created_sessions[0]
    edge = plan.proposal.created_edges[0]
    assert plan.intent == SessionArchitectureIntent.CREATE_CHILD
    assert plan.proposal.classification == SessionUpdateClassification.CREATE_CHILD
    assert child.parent_id == "app"
    assert child.root_id == "root"
    assert edge.type == EdgeType.CONTAINS
    assert edge.source_session_id == "app"
    assert edge.target_session_id == child.id


def test_plan_create_sibling_links_to_active_and_preserves_root():
    active = SessionRecord(
        id="work-a",
        kind=SessionKind.WORK,
        title="Fix auth bug",
        parent_id="goal-a",
        root_id="root-a",
    )

    plan = plan_create_sibling(active, SessionSeed(kind=SessionKind.WORK, title="Clean docs"))

    sibling = plan.proposal.created_sessions[0]
    edge = plan.proposal.created_edges[0]
    assert plan.proposal.classification == SessionUpdateClassification.CREATE_SIBLING
    assert sibling.parent_id == "goal-a"
    assert sibling.root_id == "root-a"
    assert edge.type == EdgeType.SIBLING_OF
    assert edge.source_session_id == active.id
    assert edge.target_session_id == sibling.id


def test_move_repo_under_goal_uses_non_destructive_adapter_mount():
    source = SessionRecord(id="openhands", kind=SessionKind.REPO, title="OpenHands")
    target = SessionRecord(id="goal", kind=SessionKind.GOAL, title="Integrate OpenHands")

    plan = plan_move_under(
        source,
        target,
        user_intent="Adapt executor behavior from OpenHands into this project goal.",
        mount_mode=MountMode.REFERENCE,
    )

    request = plan.proposal.mount_request
    assert request is not None
    assert plan.intent == SessionArchitectureIntent.MOVE_UNDER
    assert plan.proposal.classification == SessionUpdateClassification.ADAPT_SESSION
    assert request.source_session_id == "openhands"
    assert request.target_session_id == "goal"
    assert request.create_adaptation_session is True
    assert "Adapter projection required" in plan.warnings[0]


def test_move_same_kind_short_intent_can_plain_mount():
    source = SessionRecord(id="docs-a", kind=SessionKind.WORK, title="Docs cleanup A")
    target = SessionRecord(id="docs-b", kind=SessionKind.WORK, title="Docs cleanup B")

    plan = plan_move_under(source, target, user_intent="Group related docs cleanup.")

    assert plan.proposal.mount_request is not None
    assert plan.proposal.classification == SessionUpdateClassification.MOUNT_SESSION
    assert plan.proposal.mount_request.create_adaptation_session is False


def test_adapter_required_for_broad_source_and_focused_target():
    source = SessionRecord(id="repo", kind=SessionKind.REPO, title="Large repo")
    target = SessionRecord(id="goal", kind=SessionKind.GOAL, title="Tiny goal")

    assert adapter_required_for_move(source, target, "Use relevant behavior.") is True


def test_question_only_does_not_create_graph_changes():
    active = SessionRecord(id="goal", kind=SessionKind.GOAL, title="Explain plan")

    plan = plan_question_only(active, question="What is this session doing?")

    assert plan.proposal.classification == SessionUpdateClassification.QUESTION_ONLY
    assert plan.proposal.active_session_id == "goal"
    assert plan.proposal.created_sessions == []
    assert plan.proposal.created_edges == []
    assert plan.proposal.mount_request is None


def test_propose_context_sources_prefers_same_root_and_repo_context():
    active = SessionRecord(
        id="work",
        kind=SessionKind.WORK,
        title="Auth fix",
        summary="Need frontend repo context.",
        parent_id="goal",
        root_id="root",
    )
    repo = SessionRecord(id="repo", kind=SessionKind.REPO, title="Frontend repo", root_id="root")
    sibling = SessionRecord(
        id="sibling",
        kind=SessionKind.WORK,
        title="Sibling task",
        parent_id="goal",
        root_id="root",
    )
    unrelated = SessionRecord(id="other", kind=SessionKind.QUESTION, title="Other", root_id="other-root")

    ranked = propose_context_sources(active, [unrelated, repo, sibling])

    assert ranked[0] in {"repo", "sibling"}
    assert ranked[-1] == "other"
