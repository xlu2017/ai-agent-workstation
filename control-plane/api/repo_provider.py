"""Repository provider authentication and token selection.

This module centralizes the source of Git credentials used by repo-backed
service updates.  The dashboard can select between the legacy environment PAT
provider and GitHub OAuth without exposing either token to the browser.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

RepoProvider = Literal["personal_access_token", "github_oauth", "none"]

CONFIG_PATH = Path(os.environ.get("REPO_PROVIDER_CONFIG_PATH", "/opt/workstation/config/repo-provider.json"))
SECRETS_PATH = Path(os.environ.get("REPO_PROVIDER_SECRETS_PATH", "/opt/workstation/config/repo-provider-secrets.json"))
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pat_from_env() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT") or os.environ.get("PAT")


def _github_client_id() -> str | None:
    return os.environ.get("GITHUB_OAUTH_CLIENT_ID")


def _github_client_secret() -> str | None:
    return os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")


def _default_config() -> dict:
    return {
        "active_provider": "personal_access_token",
        "github_oauth": {
            "username": None,
            "login": None,
            "scopes": [],
            "connected_at": None,
        },
        "pending_state": None,
        "updated_at": None,
    }


def _read_json(path: Path, default: dict) -> dict:
    try:
        if not path.exists():
            return default.copy()
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else default.copy()
    except Exception:
        return default.copy()


def _write_json(path: Path, value: dict, secret: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    if secret:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    tmp.replace(path)
    if secret:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def load_repo_provider_config() -> dict:
    config = _default_config()
    config.update(_read_json(CONFIG_PATH, _default_config()))
    if config.get("active_provider") not in {"personal_access_token", "github_oauth", "none"}:
        config["active_provider"] = "personal_access_token"
    config.setdefault("github_oauth", _default_config()["github_oauth"])
    return config


def save_repo_provider_config(config: dict) -> None:
    config["updated_at"] = _now()
    _write_json(CONFIG_PATH, config)


def load_repo_provider_secrets() -> dict:
    return _read_json(SECRETS_PATH, {})


def save_repo_provider_secrets(payload: dict) -> None:
    _write_json(SECRETS_PATH, payload, secret=True)


def select_repo_provider(provider: RepoProvider) -> dict:
    config = load_repo_provider_config()
    config["active_provider"] = provider
    save_repo_provider_config(config)
    return get_repo_provider_status()


def _github_token() -> str | None:
    secrets_payload = load_repo_provider_secrets()
    value = secrets_payload.get("github_oauth", {}).get("access_token")
    return value if isinstance(value, str) and value else None


def get_repo_provider_token() -> str | None:
    """Return the selected provider token without exposing provider secrets."""
    provider = load_repo_provider_config().get("active_provider", "personal_access_token")
    if provider == "github_oauth":
        return _github_token()
    if provider == "personal_access_token":
        return _pat_from_env()
    return None


def _github_login_configured() -> bool:
    return bool(_github_client_id() and _github_client_secret())


def get_repo_provider_status() -> dict:
    config = load_repo_provider_config()
    active = config.get("active_provider", "personal_access_token")
    env_pat_available = _pat_from_env() is not None
    github_connected = _github_token() is not None
    github_configured = _github_login_configured()
    github_meta = config.get("github_oauth", {}) if isinstance(config.get("github_oauth"), dict) else {}

    providers = [
        {
            "id": "personal_access_token",
            "label": "Personal access token",
            "description": "Use GITHUB_TOKEN, GITHUB_PAT, or PAT from the server environment.",
            "configured": env_pat_available,
            "connected": env_pat_available,
            "selected": active == "personal_access_token",
            "requires_login": False,
        },
        {
            "id": "github_oauth",
            "label": "GitHub login",
            "description": "Use a GitHub OAuth login stored on the server instead of a raw environment PAT.",
            "configured": github_configured,
            "connected": github_connected,
            "selected": active == "github_oauth",
            "requires_login": True,
            "login": github_meta.get("login"),
            "username": github_meta.get("username"),
            "scopes": github_meta.get("scopes", []),
            "connected_at": github_meta.get("connected_at"),
        },
        {
            "id": "none",
            "label": "No repo provider",
            "description": "Disable repo-backed update and freshness operations.",
            "configured": True,
            "connected": False,
            "selected": active == "none",
            "requires_login": False,
        },
    ]
    return {
        "active_provider": active,
        "effective_token_available": get_repo_provider_token() is not None,
        "github_oauth_configured": github_configured,
        "providers": providers,
    }


def build_github_login_url(redirect_uri: str) -> dict:
    client_id = _github_client_id()
    if not client_id:
        return {
            "ok": False,
            "error": {
                "code": "GITHUB_OAUTH_NOT_CONFIGURED",
                "message": "Set GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET to enable GitHub login.",
            },
        }

    state = secrets.token_urlsafe(24)
    config = load_repo_provider_config()
    config["pending_state"] = state
    save_repo_provider_config(config)
    query = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "repo read:user",
        "state": state,
        "allow_signup": "true",
    })
    return {"ok": True, "login_url": f"{GITHUB_AUTHORIZE_URL}?{query}", "state": state}


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def _github_user(access_token: str) -> dict:
    request = urllib.request.Request(
        GITHUB_USER_URL,
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def complete_github_login(code: str, state: str, redirect_uri: str) -> dict:
    config = load_repo_provider_config()
    if not state or state != config.get("pending_state"):
        return {"ok": False, "error": {"code": "STATE_MISMATCH", "message": "GitHub login state did not match."}}

    client_id = _github_client_id()
    client_secret = _github_client_secret()
    if not client_id or not client_secret:
        return {"ok": False, "error": {"code": "GITHUB_OAUTH_NOT_CONFIGURED", "message": "GitHub OAuth credentials are not configured."}}

    try:
        token_payload = _post_json(GITHUB_TOKEN_URL, {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "state": state,
        })
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": {"code": "TOKEN_EXCHANGE_FAILED", "message": str(exc)[:200]}}

    access_token = token_payload.get("access_token")
    if not access_token:
        return {"ok": False, "error": {"code": "TOKEN_EXCHANGE_FAILED", "message": token_payload.get("error_description") or token_payload.get("error") or "GitHub did not return an access token."}}

    user = {}
    try:
        user = _github_user(access_token)
    except Exception:
        user = {}

    save_repo_provider_secrets({
        **load_repo_provider_secrets(),
        "github_oauth": {
            "access_token": access_token,
            "token_type": token_payload.get("token_type"),
            "scope": token_payload.get("scope", ""),
            "connected_at": _now(),
        },
    })

    scopes = [scope.strip() for scope in str(token_payload.get("scope", "")).split(",") if scope.strip()]
    config["active_provider"] = "github_oauth"
    config["pending_state"] = None
    config["github_oauth"] = {
        "login": user.get("login"),
        "username": user.get("name") or user.get("login"),
        "scopes": scopes,
        "connected_at": _now(),
    }
    save_repo_provider_config(config)
    return {"ok": True, "status": get_repo_provider_status()}


def disconnect_github_login() -> dict:
    secrets_payload = load_repo_provider_secrets()
    secrets_payload.pop("github_oauth", None)
    save_repo_provider_secrets(secrets_payload)
    config = load_repo_provider_config()
    config["github_oauth"] = _default_config()["github_oauth"]
    if config.get("active_provider") == "github_oauth":
        config["active_provider"] = "personal_access_token" if _pat_from_env() else "none"
    save_repo_provider_config(config)
    return get_repo_provider_status()
