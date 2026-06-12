"""Remote desktop routes (config, token, health)."""

import json
import urllib.error

from fastapi import APIRouter, HTTPException

from api.services.remote_desktop import (
    check_http,
    check_tcp,
    guacamole_client_identifier,
    remote_desktop_bool,
    remote_desktop_config,
    remote_desktop_env,
    request_guacamole_token,
)

router = APIRouter(tags=["remote-desktop"])


@router.get("/api/v2/remote-desktop/config")
def get_remote_desktop_config():
    return remote_desktop_config()


@router.post("/api/v2/remote-desktop/token")
def create_remote_desktop_token():
    config = remote_desktop_config()
    if not config["enabled"]:
        raise HTTPException(409, "Remote desktop is not enabled")
    if not config["auto_login"]:
        raise HTTPException(409, "Guacamole auto-login is not enabled")

    username = remote_desktop_env("GUACAMOLE_USERNAME")
    password = remote_desktop_env("GUACAMOLE_PASSWORD")
    if not username or not password:
        raise HTTPException(500, "Guacamole credentials are not configured")

    try:
        token = request_guacamole_token(username, password)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(502, f"Unable to authenticate with Guacamole: {str(exc)[:160]}") from exc

    data_source = token.get("dataSource", remote_desktop_env("GUACAMOLE_DATA_SOURCE", "postgresql"))
    connection_id = remote_desktop_env("GUACAMOLE_CONNECTION_ID", "1")
    client_id = guacamole_client_identifier(connection_id, data_source)
    guacamole_url = config["url"].rstrip("/")

    return {
        "authToken": token["authToken"],
        "username": token.get("username", username),
        "dataSource": data_source,
        "availableDataSources": token.get("availableDataSources", [data_source]),
        "connection_url": f"{guacamole_url}/#/client/{client_id}",
    }


@router.get("/api/v2/remote-desktop/health")
def get_remote_desktop_health():
    config = remote_desktop_config()
    guacamole_host = remote_desktop_env("GUACAMOLE_HOST", "127.0.0.1")
    guacamole_port = int(remote_desktop_env("GUACAMOLE_PORT", "8080"))
    guacamole_url = remote_desktop_env(
        "GUACAMOLE_HEALTH_URL",
        f"http://{guacamole_host}:{guacamole_port}/guacamole/",
    )
    rdp_host = remote_desktop_env("RDP_HOST", "dev-server")
    rdp_port = int(remote_desktop_env("RDP_PORT", "3389"))
    guacd_host = remote_desktop_env("GUACD_HOST")
    guacd_port = int(remote_desktop_env("GUACD_PORT", "4822"))

    guacamole = check_http(guacamole_url)
    rdp = check_tcp(rdp_host, rdp_port)
    guacd = check_tcp(guacd_host, guacd_port) if guacd_host else {"status": "not_configured"}

    ok = guacamole["status"] == "reachable" and rdp["status"] == "reachable"
    if guacd_host:
        ok = ok and guacd["status"] == "reachable"

    return {
        "ok": ok,
        "enabled": config["enabled"],
        "provider": "guacamole",
        "guacamole": guacamole["status"],
        "guacamole_url": guacamole_url,
        "guacd": guacd["status"],
        "rdp": rdp["status"],
        "rdp_host": rdp_host,
        "rdp_port": rdp_port,
        "details": {
            "guacamole": guacamole,
            "guacd": guacd,
            "rdp": rdp,
        },
    }
