"""Shared configuration constants for the control-plane API."""

import os
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
AGENT_CORE_URL = os.environ.get("AGENT_CORE_URL", "http://localhost:3210")
LITELLM_KEY = os.environ.get(
    "LITELLM_MASTER_KEY",
    "fdfe750a587cddaedd90f39afb861f67377b155b7fdbe5d39d53437b29a700ed",
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")

TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _get_vendor_runtime_url():
    port_file = Path("/opt/workstation/logs/openhands-port")
    if port_file.exists():
        try:
            port = int(port_file.read_text().strip())
            return f"http://localhost:{port}"
        except (ValueError, OSError):
            pass
    return "http://localhost:3010"


VENDOR_RUNTIME_URL = os.environ.get("OPENHANDS_URL") or _get_vendor_runtime_url()
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")
