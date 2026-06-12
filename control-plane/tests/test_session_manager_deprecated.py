import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sessions.session_manager import (  # noqa: E402
    DeprecatedSessionStorageError,
    SessionCreateRequest,
    create_session,
    get_session_context,
    inspect_session,
    list_sessions,
)


def test_legacy_session_manager_fails_closed():
    with pytest.raises(DeprecatedSessionStorageError):
        list_sessions()
    with pytest.raises(DeprecatedSessionStorageError):
        create_session(SessionCreateRequest(name="example"))
    with pytest.raises(DeprecatedSessionStorageError):
        inspect_session("example")
    with pytest.raises(DeprecatedSessionStorageError):
        get_session_context("example")
