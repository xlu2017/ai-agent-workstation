import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes.session_graph.dev_workflow import dev_workflow  # noqa: E402


def test_dev_workflow_allows_unscoped_start_and_requires_repo_before_execution():
    workflow = dev_workflow()["workflow"]

    assert workflow["canonical_model"] == "/api/session-graph"
    assert workflow["legacy_runtime_sessions"] == "deprecated_without_migration"
    assert workflow["repo_required_at_start"] is False
    assert workflow["repo_required_before_execution"] is True
    assert workflow["stages"] == ["goal_or_question", "repo_optional", "adapter", "work", "runtime", "validation", "pull_request"]
    assert "mounted_under" in workflow["edges"]
    assert "validates" in workflow["edges"]
