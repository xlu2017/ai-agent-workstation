import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.session_graph import EdgeType, SessionKind, SessionStatus  # noqa: E402
from api.routes.session_graph.options import get_session_graph_options  # noqa: E402


def test_session_graph_options_include_canonical_enum_values():
    options = get_session_graph_options()

    assert options["session_kinds"] == [member.value for member in SessionKind]
    assert options["session_statuses"] == [member.value for member in SessionStatus]
    assert options["edge_types"] == [member.value for member in EdgeType]
    assert "pull_request" in options["session_kinds"]
    assert "superseded" in options["session_statuses"]
    assert "semantic_alias_of" in options["edge_types"]
