import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_projection_budget_module_imports():
    module = import_module("api.services.context_projection_budget")

    assert hasattr(module, "select_context_projection_budget")
    assert hasattr(module, "ProjectionBudgetDecision")
