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


def test_context_packet_includes_browser_source_candidates():
    from ambient.context_packet import build_context_packet
    from ambient.types import AmbientEvent, AmbientSource

    event = AmbientEvent(
        event_type="browser.element_selected",
        session_id="s1",
        source=AmbientSource.BROWSER,
        actor="user",
        confidence=0.92,
        payload={
            "page": {"url": "http://localhost:5173/login", "title": "Login"},
            "selection": {
                "mode": "drag_region",
                "bounds": {"x": 10, "y": 20, "width": 120, "height": 30},
                "confidence": {"confidence": {"score": 0.92, "level": "high"}},
                "elements": [
                    {
                        "selector": "[data-testid=login-submit]",
                        "text": "Sign in",
                        "framework": "react",
                        "componentName": "LoginForm",
                        "sourceFile": "src/features/auth/LoginForm.tsx",
                        "sourceLine": 42,
                        "sourceConfidence": 0.95,
                    }
                ],
            },
        },
    )

    packet = build_context_packet("s1", [event], goal="fix this")

    assert packet.source_candidates
    assert packet.source_candidates[0]["path"] == "src/features/auth/LoginForm.tsx"
    assert packet.source_candidates[0]["line"] == 42
    assert packet.source_candidates[0]["symbol"] == "LoginForm"
    assert "src/features/auth/LoginForm.tsx" in packet.relevant_files


def test_browser_cdp_playwright_page_extracts_tab_network_console_and_ax_events():
    from ambient.collectors.browser_cdp import BrowserCdpCollector

    class FakeCdpSession:
        def send(self, method, params=None):
            if method == "Accessibility.getFullAXTree":
                return {"nodes": [{"role": {"value": "button"}, "name": {"value": "Save"}, "ignored": False}]}
            if method == "DOM.getDocument":
                return {
                    "root": {
                        "nodeName": "HTML",
                        "nodeType": 1,
                        "attributes": [],
                        "children": [
                            {
                                "nodeName": "BUTTON",
                                "nodeType": 1,
                                "attributes": ["data-testid", "save", "data-source", "src/App.tsx"],
                                "children": [],
                            }
                        ],
                    }
                }
            raise AssertionError(method)

        def detach(self):
            return None

    class FakeContext:
        def new_cdp_session(self, page):
            return FakeCdpSession()

    class FakePage:
        url = "http://localhost:5173"
        context = FakeContext()

        def title(self):
            return "App"

        def evaluate(self, script):
            return {
                "readyState": "complete",
                "title": "App",
                "url": self.url,
                "interactive": [{"tagName": "button", "text": "Save", "testId": "save"}],
                "networkRequests": [{"name": "http://localhost:5173/api/save", "initiatorType": "fetch", "duration": 12}],
                "consoleEvents": [{"level": "error", "message": "boom", "timestamp": "2026-01-01T00:00:00Z"}],
            }

    events = BrowserCdpCollector()._events_from_playwright_page(
        "s1",
        FakePage(),
        "http://127.0.0.1:9222",
        repo_id="r1",
        worktree_id="/tmp/repo",
        branch="main",
    )

    event_types = [event.event_type for event in events]
    assert event_types == ["browser.tab_observed", "browser.network_request", "browser.console_log"]
    tab = events[0]
    assert tab.payload["page_state"]["interactive"][0]["testId"] == "save"
    assert tab.payload["accessibility"]["nodes"][0]["role"] == "button"
    assert tab.payload["dom_snapshot"]["children"][0]["attributes"]["data-source"] == "src/App.tsx"
    assert events[1].payload["request"]["initiatorType"] == "fetch"
    assert events[2].payload["message"] == "boom"


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


def test_evidence_graph_links_extension_selection_to_source_file():
    from ambient.evidence_graph import build_evidence_graph
    from ambient.types import AmbientEvent, AmbientSource

    event = AmbientEvent(
        event_type="browser.element_selected",
        session_id="s1",
        source=AmbientSource.BROWSER,
        actor="user",
        confidence=0.88,
        payload={
            "page": {"url": "http://localhost:5173/login", "title": "Login"},
            "selection": {
                "mode": "drag_region",
                "elements": [
                    {
                        "selector": "[data-testid=login-submit]",
                        "componentName": "LoginForm",
                        "framework": "react",
                        "sourceFile": "src/features/auth/LoginForm.tsx",
                        "sourceLine": 42,
                    }
                ],
            },
        },
    )

    graph = build_evidence_graph([event])
    node_ids = {node.node_id for node in graph.nodes}
    relations = {edge.relation for edge in graph.edges}

    assert "dom:[data-testid=login-submit]" in node_ids
    assert "component:LoginForm" in node_ids
    assert "file:src/features/auth/LoginForm.tsx" in node_ids
    assert "observed_dom" in relations
    assert "observed_component" in relations
    assert "defined_in" in relations
