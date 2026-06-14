import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.deterministic_executor import DeterministicExecutor  # noqa: E402
from execution.runtime_validator import RuntimeValidator  # noqa: E402


def test_executor_retrieval_smoke_placeholder():
    assert DeterministicExecutor is not None


def test_retrieval_alias_set_is_available_without_bridge_default_update():
    aliases = RuntimeValidator._action_is_allowed
    validator = object.__new__(RuntimeValidator)
    assert aliases(validator, "read_file_range", ["read_file"])
    assert aliases(validator, "glob", ["list_files"])
    assert aliases(validator, "find_files", ["search_code"])
