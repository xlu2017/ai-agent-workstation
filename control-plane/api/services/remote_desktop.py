"""Shared remote desktop helpers (Guacamole config, token, health checks)."""

import base64
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from api.config import TRUE_ENV_VALUES

REMOTE_DESKTOP_ENV_FILE = Path(
    os.environ.get(
        "REMOTE_DESKTOP_ENV_FILE",
        "/opt/workstation/repos/jubilant-goggles/ops/remote-desktop/.env",
    )
)


def _remote_desktop_file_env() -> dict[str, str]:
    if not REMOTE_DESKTOP_ENV_FILE.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = REMOTE_DESKTOP_ENV_FILE.read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def remote_desktop_env(name: str, default: str = "") -> str:
    return os.environ.get(name) or _remote_desktop_file_env().get(name, default)


def remote_desktop_bool(name: str, default: bool = False) -> bool:
    value = remote_desktop_env(name)
    if value == "":
        return default
    return value.strip().lower() in TRUE_ENV_VALUES


def remote_desktop_config() -> dict:
    return {
        "enabled": remote_desktop_bool("REMOTE_DESKTOP_ENABLED", False),
        "provider": "guacamole",
        "url": remote_desktop_env("GUACAMOLE_URL", "/guacamole/"),
        "rdp_host": remote_desktop_env("RDP_HOST", "dev-server"),
        "security": "tailscale_only",
        "auto_login": remote_desktop_bool("GUACAMOLE_AUTO_LOGIN_ENABLED", False),
    }


def guacamole_client_identifier(connection_id: str, data_source: str) -> str:
    raw_identifier = f"{connection_id}\0c\0{data_source}".encode()
    return base64.b64encode(raw_identifier).decode().rstrip("=")


def request_guacamole_token(username: str, password: str):
    guacamole_host = remote_desktop_env("GUACAMOLE_HOST", "127.0.0.1")
    guacamole_port = int(remote_desktop_env("GUACAMOLE_PORT", "8080"))
    token_url = f"http://{guacamole_host}:{guacamole_port}/guacamole/api/tokens"
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5.0) as response:
        return json.loads(response.read().decode())


def check_tcp(host: str, port: int, timeout: float = 3.0) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"status": "reachable"}
    except OSError as exc:
        return {"status": "unreachable", "error": str(exc)[:160]}


def check_http(url: str, timeout: float = 3.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"status": "reachable", "code": response.status}
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            return {"status": "reachable", "code": exc.code}
        return {"status": "unreachable", "code": exc.code, "error": str(exc)[:160]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": "unreachable", "error": str(exc)[:160]}
