import sys
import tempfile
from pathlib import Path

# Add control-plane root to path
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_redaction_removes_secret_values():
    from ambient.redaction import redact_payload

    payload, privacy = redact_payload({
        "headers": {"authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
        "text": "password=supersecret",
    })

    assert payload["headers"]["authorization"] == "[redacted]"
    assert "supersecret" not in payload["text"]
    assert privacy.contains_secret is True
    assert privacy.redaction_applied is True


def test_context_packet_prefers_editor_selection_focus():
    from ambient.collectors.browser_cdp import build_element_selected_event
    from ambient.collectors.editor_bridge import build_editor_selection_event
    from ambient.context_packet import build_context_packet

    browser_event = build_element_selected_event(
        "s1",
        url="http://localhost:5173/login",
        selector="[data-testid='login-submit']",
        component={"name": "LoginForm", "source": "src/LoginForm.tsx", "line": 42},
    )
    editor_event = build_editor_selection_event(
        "s1",
        path="src/LoginForm.tsx",
        start_line=41,
        end_line=45,
        selected_text="submitLogin()",
    )

    packet = build_context_packet("s1", [browser_event, editor_event], goal="fix this")

    assert packet.ambient_focus is not None
    assert packet.ambient_focus["kind"] == "editor.selection_changed"
    assert "src/LoginForm.tsx" in packet.relevant_files
    assert packet.goal == "fix this"


def test_ambient_event_persistence_mirrors_live_feed():
    from ambient.collectors.terminal_collector import TerminalObservationBuilder
    from ambient.event_log import load_ambient_events, persist_ambient_event
    from live_feed.events import EventStore, EventType

    with tempfile.TemporaryDirectory() as tmpdir:
        event = TerminalObservationBuilder().command_completed(
            "s1",
            terminal_id="term-1",
            cwd="/tmp/repo",
            command="pytest",
            exit_code=1,
            stderr="FAILED tests/test_login.py::test_login",
        )
        persist_ambient_event(event, sessions_dir=tmpdir)

        ambient_events = load_ambient_events("s1", sessions_dir=tmpdir)
        mirrored = EventStore(tmpdir).get_events(
            "s1", event_types=[EventType.AMBIENT_CONTEXT_COLLECTED]
        )

        assert len(ambient_events) == 1
        assert ambient_events[0].payload["mentioned_files"] == ["tests/test_login.py"]
        assert len(mirrored) == 1
        assert mirrored[0]["data"]["ambient_event_type"] == "terminal.command_completed"


def test_evidence_graph_links_component_to_source_file():
    from ambient.collectors.browser_cdp import build_element_selected_event
    from ambient.evidence_graph import build_evidence_graph

    event = build_element_selected_event(
        "s1",
        url="http://localhost:5173/login",
        selector="button[type=submit]",
        component={"name": "LoginForm", "source": "src/features/auth/LoginForm.tsx"},
    )
    graph = build_evidence_graph([event])

    node_ids = {node.node_id for node in graph.nodes}
    relations = {edge.relation for edge in graph.edges}

    assert "component:LoginForm" in node_ids
    assert "file:src/features/auth/LoginForm.tsx" in node_ids
    assert "defined_in" in relations
