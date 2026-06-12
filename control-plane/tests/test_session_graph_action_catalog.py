import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import EdgeType, MountMode, SessionKind, SessionRecord  # noqa: E402
from api.services.session_action_catalog import (  # noqa: E402
    execute_session_action,
    get_session_action,
    session_action_catalog,
    validate_session_action_params,
)
from api.services.session_graph_service import SessionGraphStore  # noqa: E402


def _store(tmp_path: Path) -> SessionGraphStore:
    os.environ["SESSION_GRAPH_PATH"] = str(tmp_path / "session-graph.json")
    return SessionGraphStore()


def _seed_sessions(store: SessionGraphStore) -> None:
    store.create_session(SessionRecord(id="repo-session", kind=SessionKind.REPO, title="Repo"))
    store.create_session(SessionRecord(id="goal-session", kind=SessionKind.GOAL, title="Goal"))


def _mount_params() -> dict[str, object]:
    return {
        "source_session_id": "repo-session",
        "target_session_id": "goal-session",
        "user_intent": "Use repo context to implement the goal.",
        "mount_mode": MountMode.REFERENCE.value,
        "create_adaptation_session": True,
        "make_active": False,
    }


def test_session_action_catalog_exposes_mount_actions():
    catalog = session_action_catalog()
    names = [action["name"] for action in catalog["actions"]]

    assert catalog["canonical"] is True
    assert catalog["executor_scope"] == "session_graph"
    assert "session.mount" in names
    assert "session.mount.preview" in names
    assert get_session_action("session.mount")["executor"] == "session_graph.mount_session"


def test_session_mount_action_validates_params():
    validation = validate_session_action_params("session.mount", _mount_params())

    assert validation["ok"] is True
    assert validation["action"]["name"] == "session.mount"


def test_session_mount_action_persists_graph_edge(tmp_path):
    store = _store(tmp_path)
    _seed_sessions(store)

    preview = execute_session_action(store, "session.mount.preview", _mount_params())
    assert preview["preview"] is True
    assert store.load().edges == []

    applied = execute_session_action(store, "session.mount", _mount_params())
    graph = store.load()

    assert applied["preview"] is False
    assert any(edge.type == EdgeType.MOUNTED_UNDER for edge in graph.edges)
    assert graph.projections
    assert any(session.kind == SessionKind.ADAPTER for session in graph.sessions)


def test_session_unmount_action_removes_mounted_edge(tmp_path):
    store = _store(tmp_path)
    _seed_sessions(store)
    execute_session_action(store, "session.mount", _mount_params())

    removed = execute_session_action(
        store,
        "session.unmount",
        {
            "source_session_id": "repo-session",
            "target_session_id": "goal-session",
            "reason": "test cleanup",
        },
    )

    graph = store.load()
    assert removed["result"]["removed_edge_ids"]
    assert not any(edge.type == EdgeType.MOUNTED_UNDER for edge in graph.edges)
