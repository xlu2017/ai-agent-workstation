"""Configurable repository source registry for repo-backed services.

This registry separates two decisions that were previously conflated:

1. repo credential provider: personal access token, GitHub OAuth, or none
2. repo source: which owner/repo/branch/path a service should update from

The default service definitions are only seed data. Operators can override them
through a JSON registry file or environment variables without changing code.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(os.environ.get("REPO_SOURCE_REGISTRY_PATH", "/opt/workstation/config/repo-sources.json"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _service_default_path(service: str) -> str:
    return _env(f"{service.upper().replace('-', '_')}_REPO_PATH", f"/opt/workstation/repos/{service}") or f"/opt/workstation/repos/{service}"


def _default_service_sources() -> dict[str, dict[str, Any]]:
    """Return seed service source data.

    Repo identity is represented as owner/repo data, not embedded in update
    logic. Legacy URL/path environment variables still work as migration shims.
    """
    agent_owner = _env("AGENT_CORE_REPO_OWNER", "xlu2017")
    agent_repo = _env("AGENT_CORE_REPO_NAME", "agent-core")
    app_owner = _env("AGENT_WORKSTATION_REPO_OWNER", "xlu2017")
    app_repo = _env("AGENT_WORKSTATION_REPO_NAME", "ai-agent-workstation")
    app_path = _env("AGENT_WORKSTATION_REPO_PATH", "/opt/workstation/repos/ai-agent-workstation")

    return {
        "agent-core": {
            "service": "agent-core",
            "enabled": True,
            "repo_provider": "github",
            "owner": agent_owner,
            "repo": agent_repo,
            "repo_url": _env("AGENT_CORE_REPO_URL"),
            "branch": _env("AGENT_CORE_UPDATE_BRANCH"),
            "path": _env("AGENT_CORE_REPO_PATH", _service_default_path("agent-core")),
            "install_commands": ["pnpm install --frozen-lockfile"],
            "build_commands": ["pnpm build"],
            "restart_command": "fuser -k 3210/tcp; sleep 1; cd {path} && nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
        },
        "dashboard": {
            "service": "dashboard",
            "enabled": True,
            "repo_provider": "github",
            "owner": app_owner,
            "repo": app_repo,
            "repo_url": _env("AGENT_WORKSTATION_REPO_URL"),
            "branch": _env("AGENT_WORKSTATION_UPDATE_BRANCH"),
            "path": app_path,
            "install_commands": [
                "pnpm install --frozen-lockfile",
                "(cd control-plane/web && pnpm install --frozen-lockfile)",
                "rsync -a --delete --exclude node_modules control-plane/web/ /opt/workstation/control-plane/web/",
                "(cd /opt/workstation/control-plane/web && pnpm install --frozen-lockfile)",
            ],
            "build_commands": ["(cd /opt/workstation/control-plane/web && pnpm build)"],
            "restart_command": "fuser -k 5173/tcp; sleep 1; cd /opt/workstation/control-plane/web && nohup pnpm dev --host 0.0.0.0 --port 5173 > /opt/workstation/logs/dashboard.log 2>&1 &",
        },
        "control-plane": {
            "service": "control-plane",
            "enabled": True,
            "repo_provider": "github",
            "owner": app_owner,
            "repo": app_repo,
            "repo_url": _env("AGENT_WORKSTATION_REPO_URL"),
            "branch": _env("AGENT_WORKSTATION_UPDATE_BRANCH"),
            "path": app_path,
            "install_commands": ["pnpm install --frozen-lockfile"],
            "build_commands": [],
            "restart_command": "fuser -k 9877/tcp; sleep 1; cd {path}/control-plane && nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload > /opt/workstation/logs/control-plane.log 2>&1 &",
        },
    }


def _default_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "services": _default_service_sources(),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_repo_source_registry() -> dict[str, Any]:
    registry = _default_registry()
    persisted = _read_json(REGISTRY_PATH)
    if persisted:
        registry = _deep_merge(registry, persisted)
    registry.setdefault("services", {})
    return registry


def save_repo_source_registry(registry: dict[str, Any]) -> dict[str, Any]:
    registry = copy.deepcopy(registry)
    registry["version"] = int(registry.get("version") or 1)
    registry["updated_at"] = _now()
    registry.setdefault("services", {})
    _write_json(REGISTRY_PATH, registry)
    return registry


def repo_url_for_source(source: dict[str, Any]) -> str:
    explicit = source.get("repo_url")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    provider = source.get("repo_provider", "github")
    owner = str(source.get("owner") or "").strip()
    repo = str(source.get("repo") or "").strip()
    if provider == "github" and owner and repo:
        repo_name = repo[:-4] if repo.endswith(".git") else repo
        return f"https://github.com/{owner}/{repo_name}.git"
    return ""


def normalize_source(service_name: str, source: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(source)
    normalized["service"] = service_name
    normalized.setdefault("enabled", True)
    normalized.setdefault("repo_provider", "github")
    normalized.setdefault("branch", None)
    normalized.setdefault("install_commands", [])
    normalized.setdefault("build_commands", [])
    normalized.setdefault("restart_command", "")
    normalized["path"] = str(normalized.get("path") or _service_default_path(service_name))
    normalized["repo_url"] = repo_url_for_source(normalized)
    if "{path}" in str(normalized.get("restart_command") or ""):
        normalized["restart_command"] = str(normalized["restart_command"]).format(path=normalized["path"])
    return normalized


def list_repo_sources() -> dict[str, dict[str, Any]]:
    registry = load_repo_source_registry()
    return {
        service_name: normalize_source(service_name, source)
        for service_name, source in registry.get("services", {}).items()
        if isinstance(source, dict)
    }


def get_repo_source(service_name: str) -> dict[str, Any] | None:
    return list_repo_sources().get(service_name)


def get_service_update_config(service_name: str) -> dict[str, Any] | None:
    source = get_repo_source(service_name)
    if not source or not source.get("enabled", True):
        return None
    if not source.get("repo_url"):
        return None
    return {
        "repo_url": source["repo_url"],
        "branch": source.get("branch"),
        "path": source["path"],
        "install_commands": source.get("install_commands", []),
        "build_commands": source.get("build_commands", []),
        "restart_command": source.get("restart_command", ""),
        "repo_provider": source.get("repo_provider", "github"),
        "owner": source.get("owner"),
        "repo": source.get("repo"),
        "service": service_name,
    }


def get_all_service_update_configs() -> dict[str, dict[str, Any]]:
    return {
        service_name: config
        for service_name in list_repo_sources().keys()
        if (config := get_service_update_config(service_name)) is not None
    }


def update_repo_source(service_name: str, patch: dict[str, Any]) -> dict[str, Any]:
    allowed = {"enabled", "repo_provider", "owner", "repo", "repo_url", "branch", "path", "install_commands", "build_commands", "restart_command"}
    registry = load_repo_source_registry()
    services = registry.setdefault("services", {})
    current = copy.deepcopy(services.get(service_name) or _default_service_sources().get(service_name) or {"service": service_name})
    for key, value in patch.items():
        if key in allowed:
            current[key] = value
    services[service_name] = current
    save_repo_source_registry(registry)
    return normalize_source(service_name, current)


def reset_repo_source(service_name: str) -> dict[str, Any]:
    defaults = _default_service_sources()
    if service_name not in defaults:
        raise KeyError(service_name)
    registry = load_repo_source_registry()
    registry.setdefault("services", {})[service_name] = defaults[service_name]
    save_repo_source_registry(registry)
    return normalize_source(service_name, defaults[service_name])
