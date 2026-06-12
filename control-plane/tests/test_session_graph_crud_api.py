import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import (  # noqa: E402
    ContextProjection,
    ContextProjectionBudget,
    EdgeType,
    ProjectionMode,
    SessionKind,
    SessionRecord,
    SessionStatus,
)
from api.session_graph import (  # noqa: E402
    CreateEdgeRequest,
    RequestContext,
    UpdateEdgeRequest,
    UpdateProjectionRequest,
    UpdateSessionRequest,
    create_context_projection,
    create_session,
    create_session_edge,
    delete_context_projection,
    delete_session,
    delete_session_edge,
    get_context_projection_by_id,
    get_session_edge,
    update_context_projection,
    update_session,
    update_session_edge,
)


def _use_graph_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SESSION_GRAPH_PATH", str(tmp_path / "session-graph.json"))


def _ctx() -> RequestContext:
    return RequestContext(workspace_id="workspace-a", user_id="user-a")


def test_session_crud_update_and_delete(monkeypatch, tmp_path: Path):
    _use_graph_path(monkeypatch, tmp_path)
    context = _ctx()

    created = create_session(SessionRecord(id="goal-a", kind=SessionKind.GOAL, title="Old goal"), context=context)
    assert created["session"]["metadata"]["workspace_id"] == "workspace-a"

    updated = update_session(
        "goal-a",
        UpdateSessionRequest(title="New goal", status=SessionStatus.ACTIVE, state={"scope_status": "scoped"}),
        context=context,
    )
    assert updated["session"]["title"] == "New goal"
    assert updated["session"]["status"] == "active"
    assert updated["session"]["state"]["scope_status"] == "scoped"

    deleted = delete_session("goal-a", cascade=False, context=context)
    assert deleted["deleted_session_ids"] == ["goal-a"]


def test_edge_crud_update_and_delete(monkeypatch, tmp_path: Path):
    _use_graph_path(monkeypatch, tmp_path)
    context = _ctx()
    create_session(SessionRecord(id="repo-a", kind=SessionKind.REPO, title="Repo"), context=context)
    create_session(SessionRecord(id="goal-a", kind=SessionKind.GOAL, title="Goal"), context=context)

    created = create_session_edge(
        CreateEdgeRequest(type=EdgeType.REFERENCES, source_session_id="repo-a", target_session_id="goal-a"),
        context=context,
    )
    edge_id = created["edge"]["id"]
    assert get_session_edge(edge_id, context=context)["edge"]["type"] == "references"

    updated = update_session_edge(edge_id, UpdateEdgeRequest(type=EdgeType.DEPENDS_ON), context=context)
    assert updated["edge"]["type"] == "depends_on"

    deleted = delete_session_edge(edge_id, context=context)
    assert deleted["deleted_edge_id"] == edge_id


def test_projection_crud_update_and_delete(monkeypatch, tmp_path: Path):
    _use_graph_path(monkeypatch, tmp_path)
    context = _ctx()
    create_session(SessionRecord(id="repo-a", kind=SessionKind.REPO, title="Repo"), context=context)
    create_session(SessionRecord(id="goal-a", kind=SessionKind.GOAL, title="Goal"), context=context)

    created = create_context_projection(
        ContextProjection(
            id="projection-a",
            active_session_id="goal-a",
            source_session_ids=["repo-a"],
            projection_mode=ProjectionMode.SUMMARY,
            budget=ContextProjectionBudget(max_tokens=1000, max_files=4, max_events=10),
            rationale="Small bounded projection for tests.",
        ),
        context=context,
    )
    assert created["projection"]["id"] == "projection-a"

    updated = update_context_projection(
        "projection-a",
        UpdateProjectionRequest(relevance_score=0.9, rationale="Updated projection."),
        context=context,
    )
    assert updated["projection"]["relevance_score"] == 0.9
    assert get_context_projection_by_id("projection-a", context=context)["projection"]["rationale"] == "Updated projection."

    deleted = delete_context_projection("projection-a", context=context)
    assert deleted["deleted_projection_id"] == "projection-a"
