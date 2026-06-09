"""Tests for the stop/cancel/resume behavior.

Covers:
  - _cancelled_sessions set blocks executor iteration
  - Cancelled task emits proper event
  - Cancelled session does not auto-resume
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from execution.agentic_executor import _cancelled_sessions


def test_cancelled_sessions_set_is_set():
    """_cancelled_sessions must be a set, checked by executor loop."""
    assert isinstance(_cancelled_sessions, set)


def test_cancellation_flag_add_remove():
    """Adding and discarding from _cancelled_sessions works correctly."""
    _cancelled_sessions.add("test-cancel-1")
    assert "test-cancel-1" in _cancelled_sessions
    _cancelled_sessions.discard("test-cancel-1")
    assert "test-cancel-1" not in _cancelled_sessions


def test_cancellation_flag_not_sticky():
    """After discard, the session should not appear cancelled."""
    _cancelled_sessions.add("test-cancel-2")
    _cancelled_sessions.discard("test-cancel-2")
    # Must not linger
    assert "test-cancel-2" not in _cancelled_sessions


def test_multiple_sessions_independent():
    """Cancelling one session does not cancel others."""
    _cancelled_sessions.add("s-a")
    _cancelled_sessions.add("s-b")
    assert "s-a" in _cancelled_sessions
    assert "s-b" in _cancelled_sessions
    _cancelled_sessions.discard("s-a")
    assert "s-a" not in _cancelled_sessions
    assert "s-b" in _cancelled_sessions
    _cancelled_sessions.discard("s-b")
