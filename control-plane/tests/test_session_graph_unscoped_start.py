import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import SessionKind, SessionRecord  # noqa: E402
from api.services.session_graph_service import SessionGraphStore  # noqa: E402


def test_goal_session_can_start_without_repo_scope(tmp_path):
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    store = SessionGraphStore()

    created = store.create_session(
        SessionRecord(
            id="goal-unscoped",
            kind=SessionKind.GOAL,
            title="Investigate product direction",
            summary="This session intentionally starts without repo scope.",
        )
    )

    assert created.id == "goal-unscoped"
    assert created.parent_id is None
    assert created.root_id == "goal-unscoped"
    assert store.get_session("goal-unscoped") is not None
