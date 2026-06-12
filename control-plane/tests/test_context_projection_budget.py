import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_projection_budget_module_imports():
    module = import_module("api.services.context_projection_budget")

    assert hasattr(module, "select_context_projection_budget")
    assert hasattr(module, "ProjectionBudgetDecision")


def test_projection_budget_profiles_are_selected():
    models = import_module("api.models.session_graph")
    budget = import_module("api.services.context_projection_budget")

    runtime = models.SessionRecord(id="runtime", kind=models.SessionKind.RUNTIME, title="Runtime")
    repo = models.SessionRecord(id="repo", kind=models.SessionKind.REPO, title="Repo")
    goal = models.SessionRecord(id="goal", kind=models.SessionKind.GOAL, title="Goal")
    app = models.SessionRecord(id="app", kind=models.SessionKind.APP, title="App")

    direct = budget.select_context_projection_budget(runtime, runtime, models.MountMode.REFERENCE, "direct ui operation")
    bugfix = budget.select_context_projection_budget(repo, goal, models.MountMode.REFERENCE, "fix failing test")
    architecture = budget.select_context_projection_budget(repo, goal, models.MountMode.REFERENCE, "design architecture")
    integration = budget.select_context_projection_budget(repo, app, models.MountMode.COMPONENT, "integrate interface")

    assert direct.profile == "direct_ui_action"
    assert direct.budget.max_tokens == 1000
    assert bugfix.profile == "known_repo_bug_fix"
    assert 4000 <= bugfix.budget.max_tokens <= 8000
    assert architecture.profile == "architecture_planning"
    assert architecture.budget.max_events == 200
    assert integration.profile == "cross_repo_integration"
    assert integration.budget.max_tokens >= 20000


def test_budgeted_projection_records_dominance_guard_evidence():
    models = import_module("api.models.session_graph")
    projection_service = import_module("api.services.context_projection_service")

    repo = models.SessionRecord(id="repo", kind=models.SessionKind.REPO, title="Large repo")
    goal = models.SessionRecord(id="goal", kind=models.SessionKind.GOAL, title="Small goal")
    request = models.MountSessionRequest(
        source_session_id="repo",
        target_session_id="goal",
        user_intent="use termination behavior",
        mount_mode=models.MountMode.REFERENCE,
        create_adaptation_session=True,
    )

    projection = projection_service.generate_budgeted_context_projection(repo, goal, request)

    assert projection.budget.max_tokens == 4000
    assert "budget_profile:focused_mount_projection" in projection.evidence
    assert "dominance_guard:broad_source_under_focused_target" in projection.evidence
    assert "unrelated_capabilities" in [selector.value for selector in projection.exclude_selectors]
