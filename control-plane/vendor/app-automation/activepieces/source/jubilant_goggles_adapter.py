#!/usr/bin/env python3
"""Jubilant Goggles local contract adapter for the vendored Activepieces source tree."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

VENDOR_ID = "activepieces"
SUPPORTED_ACTIONS = {
    "google_sheets.append_row",
    "jira.create_issue",
    "discord.send_message",
    "slack.send_message",
}


def _read_envelope() -> dict[str, Any]:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def _response(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("__health"):
        return {
            "ok": True,
            "status": "available",
            "message": "Vendored Activepieces contract adapter is available.",
            "result": {"vendor": VENDOR_ID, "supported_actions": sorted(SUPPORTED_ACTIONS)},
        }

    action_id = str(envelope.get("action_id") or "")
    params = envelope.get("params") if isinstance(envelope.get("params"), dict) else {}
    if action_id not in SUPPORTED_ACTIONS:
        return {
            "ok": False,
            "status": "action_not_supported_by_local_adapter",
            "message": f"{VENDOR_ID} local adapter does not support {action_id}.",
            "error": {"code": "ACTION_NOT_SUPPORTED_BY_LOCAL_ADAPTER", "message": f"Unsupported action: {action_id}"},
        }

    return {
        "ok": True,
        "status": "adapter_contract_completed",
        "message": f"Vendored {VENDOR_ID} adapter accepted {action_id}. Configure ACTIVEPIECES_WEBHOOK_URL for live workflow execution.",
        "planned_steps": [
            "Accepted normalized Jubilant Goggles action envelope.",
            "Mapped action into the Activepieces workflow/piece layer.",
            "Stopped at the local vendored adapter boundary without external side effects.",
        ],
        "result": {
            "vendor": VENDOR_ID,
            "action_id": action_id,
            "contract": "jubilant_goggles_app_automation_v1",
            "external_side_effect_performed": False,
            "params_keys": sorted(params.keys()),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def main() -> int:
    try:
        envelope = _read_envelope()
        print(json.dumps(_response(envelope), ensure_ascii=False))
        return 0
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "status": "adapter_error", "message": str(exc), "error": {"code": "ADAPTER_ERROR", "message": str(exc)}}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
