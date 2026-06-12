"""
Local gate-token lookup for runtime-gated actions.

This module lets RuntimeValidator verify that high-risk platform actions carry
a session-scoped evidence file before execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VALID_GATE_STATES = {"ok", "granted", "approved"}


def gate_path(sessions_dir: str | Path, session_id: str, gate_id: str) -> Path:
    return Path(sessions_dir) / session_id / "gates" / f"{gate_id}.json"


def gate_is_valid(
    sessions_dir: str | Path,
    session_id: str,
    action_name: str,
    gate_id: str,
) -> tuple[bool, str]:
    if not gate_id:
        return False, "Gate evidence is required"

    path = gate_path(sessions_dir, session_id, gate_id)
    if not path.exists():
        return False, f"Gate evidence not found: {gate_id}"

    try:
        data: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Gate evidence is unreadable: {exc}"

    state = str(data.get("status", data.get("state", ""))).lower()
    if state not in VALID_GATE_STATES:
        return False, f"Gate {gate_id} is not active"

    gated_action = str(data.get("action", data.get("action_name", "")))
    if gated_action and gated_action != action_name:
        return False, f"Gate {gate_id} is for {gated_action}, not {action_name}"

    return True, ""
