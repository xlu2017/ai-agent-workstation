"""Runtime configuration store for app-automation vendors.

The control plane can route actions into vendored local adapters without external
configuration. Live external execution still needs a vendor endpoint or command.
This module persists those operator-supplied values outside source control so the
UI can present a concrete configuration dialog when a selected vendor is not
configured.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

RuntimeConfigKind = Literal["url", "command", "provider"]

CONFIG_PATH = Path(os.environ.get("APP_AUTOMATION_CONFIG_PATH", "/opt/workstation/config/app-automation-runtime.json"))


class AppAutomationVendorConfigInput(BaseModel):
    value: str = Field(default="", description="Endpoint URL or command string for this vendor runtime.")
    enabled: bool = True


VENDOR_RUNTIME_FIELDS: dict[str, dict[str, Any]] = {
    "composio": {
        "env_name": "COMPOSIO_PROXY_URL",
        "kind": "url",
        "label": "Composio proxy URL",
        "description": "Controlled HTTP endpoint that accepts normalized Composio action envelopes.",
        "placeholder": "https://internal.example/app-automation/composio",
    },
    "activepieces": {
        "env_name": "ACTIVEPIECES_WEBHOOK_URL",
        "kind": "url",
        "label": "Activepieces webhook URL",
        "description": "Controlled workflow endpoint that accepts normalized Activepieces action envelopes.",
        "placeholder": "https://internal.example/hooks/activepieces",
    },
    "n8n": {
        "env_name": "N8N_WEBHOOK_URL",
        "kind": "url",
        "label": "n8n webhook URL",
        "description": "Controlled n8n webhook endpoint that accepts normalized action envelopes.",
        "placeholder": "https://internal.example/webhook/jubilant-goggles",
    },
    "stagehand": {
        "env_name": "STAGEHAND_COMMAND",
        "kind": "command",
        "label": "Stagehand command",
        "description": "Command run from the vendored Stagehand source tree. It receives a JSON envelope on stdin.",
        "placeholder": "pnpm tsx scripts/jubilant-adapter.ts",
    },
    "browser_use": {
        "env_name": "BROWSER_USE_COMMAND",
        "kind": "command",
        "label": "Browser Use command",
        "description": "Command run from the vendored Browser Use source tree. It receives a JSON envelope on stdin.",
        "placeholder": "python scripts/jubilant_adapter.py",
    },
    "skyvern": {
        "env_name": "SKYVERN_COMMAND",
        "kind": "command",
        "label": "Skyvern command",
        "description": "Command run from the vendored Skyvern source tree. It receives a JSON envelope on stdin.",
        "placeholder": "python scripts/jubilant_adapter.py",
    },
    "mcp_servers": {
        "env_name": None,
        "kind": "provider",
        "label": "GitHub repo provider auth",
        "description": "MCP/GitHub live execution uses the server-side repository provider token instead of a vendor-specific endpoint.",
        "placeholder": "Configure GitHub auth in Repo Provider settings.",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_config() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.exists():
            return {"version": 1, "updated_at": None, "vendors": {}}
        value = json.loads(CONFIG_PATH.read_text())
        if isinstance(value, dict):
            value.setdefault("version", 1)
            value.setdefault("vendors", {})
            return value
    except Exception:
        pass
    return {"version": 1, "updated_at": None, "vendors": {}}


def _write_config(config: dict[str, Any]) -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    persisted = copy.deepcopy(config)
    persisted["version"] = int(persisted.get("version") or 1)
    persisted["updated_at"] = _now()
    persisted.setdefault("vendors", {})
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n")
    tmp.replace(CONFIG_PATH)
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    return persisted


def _env_value(vendor_id: str) -> str | None:
    meta = VENDOR_RUNTIME_FIELDS.get(vendor_id, {})
    env_name = meta.get("env_name")
    if not env_name:
        return None
    value = os.environ.get(str(env_name))
    return value if value else None


def _stored_vendor_config(vendor_id: str) -> dict[str, Any] | None:
    value = _read_config().get("vendors", {}).get(vendor_id)
    return value if isinstance(value, dict) else None


def _preview(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 12:
        return "••••"
    return f"{value[:6]}…{value[-4:]}"


def get_runtime_value(vendor_id: str) -> str | None:
    env_value = _env_value(vendor_id)
    if env_value:
        return env_value
    stored = _stored_vendor_config(vendor_id)
    if not stored or stored.get("enabled") is False:
        return None
    value = str(stored.get("value") or "").strip()
    return value or None


def get_runtime_config_source(vendor_id: str) -> str:
    if _env_value(vendor_id):
        return "environment"
    if get_runtime_value(vendor_id):
        return "stored"
    if VENDOR_RUNTIME_FIELDS.get(vendor_id, {}).get("kind") == "provider":
        return "provider"
    return "unconfigured"


def vendor_config_status(vendor_id: str) -> dict[str, Any]:
    meta = VENDOR_RUNTIME_FIELDS.get(vendor_id, {})
    source = get_runtime_config_source(vendor_id)
    stored = _stored_vendor_config(vendor_id)
    value = _env_value(vendor_id) or (str(stored.get("value") or "") if stored else None)
    return {
        "vendor_id": vendor_id,
        "configurable": bool(meta.get("env_name")),
        "configured": source in {"environment", "stored", "provider"},
        "config_source": source,
        "env_name": meta.get("env_name"),
        "kind": meta.get("kind", "url"),
        "label": meta.get("label", vendor_id),
        "description": meta.get("description", ""),
        "placeholder": meta.get("placeholder", ""),
        "value_preview": _preview(value),
        "stored_enabled": bool(stored.get("enabled", True)) if stored else False,
        "can_edit": source != "environment" and bool(meta.get("env_name")),
    }


def all_vendor_config_status() -> dict[str, Any]:
    config = _read_config()
    return {
        "config_path": str(CONFIG_PATH),
        "updated_at": config.get("updated_at"),
        "vendors": [vendor_config_status(vendor_id) for vendor_id in VENDOR_RUNTIME_FIELDS.keys()],
    }


def save_vendor_config(vendor_id: str, body: AppAutomationVendorConfigInput) -> dict[str, Any]:
    if vendor_id not in VENDOR_RUNTIME_FIELDS:
        raise KeyError(vendor_id)
    if not VENDOR_RUNTIME_FIELDS[vendor_id].get("env_name"):
        raise ValueError(f"{vendor_id} is not configured through a vendor-specific endpoint or command.")
    value = body.value.strip()
    if body.enabled and not value:
        raise ValueError("Configuration value is required when enabled=true.")
    config = _read_config()
    vendors = config.setdefault("vendors", {})
    vendors[vendor_id] = {
        "enabled": bool(body.enabled),
        "value": value,
        "updated_at": _now(),
    }
    _write_config(config)
    return vendor_config_status(vendor_id)


def clear_vendor_config(vendor_id: str) -> dict[str, Any]:
    if vendor_id not in VENDOR_RUNTIME_FIELDS:
        raise KeyError(vendor_id)
    config = _read_config()
    vendors = config.setdefault("vendors", {})
    vendors.pop(vendor_id, None)
    _write_config(config)
    return vendor_config_status(vendor_id)
