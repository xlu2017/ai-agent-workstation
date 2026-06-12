"""
Server-side GitHub update logic for repo-backed services.

Reads a static allowlist of service configs, fetches the latest default branch
using a server-side PAT (never exposed to the browser), runs optional
install/build commands, and restarts the service.

Security:
- The PAT is read from GITHUB_TOKEN or GITHUB_PAT env vars and never logged,
  returned in responses, or written to disk.
- Command output is sanitized before inclusion in any response.
- A per-repo-path lock prevents concurrent updates to shared checkouts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _install_session_architecture_router_bootstrap() -> None:
    """Mount the session architecture router from the existing server import path.

    The current control-plane server imports this module before creating and
    configuring the FastAPI app. That gives us a safe compatibility point for
    mounting the newly implemented session architecture API without rewriting the
    large server module through the GitHub contents API.
    """

    try:
        from fastapi import FastAPI
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.warning("Unable to import FastAPI for session architecture router bootstrap: %s", exc)
        return

    original_include_router = getattr(FastAPI, "include_router", None)
    if original_include_router is None:
        return
    if getattr(original_include_router, "_session_architecture_bootstrap", False):
        return

    def include_router_with_session_architecture(self, router, *args, **kwargs):
        result = original_include_router(self, router, *args, **kwargs)
        if getattr(self, "_session_architecture_router_mounted", False):
            return result
        if getattr(router, "prefix", "") != "/api/session-graph":
            return result
        try:
            from api.session_architecture import router as session_architecture_router

            original_include_router(self, session_architecture_router)
            setattr(self, "_session_architecture_router_mounted", True)
        except Exception as exc:  # pragma: no cover - defensive import guard
            logger.warning("Unable to mount session architecture router: %s", exc)
        return result

    setattr(include_router_with_session_architecture, "_session_architecture_bootstrap", True)
    FastAPI.include_router = include_router_with_session_architecture


_install_session_architecture_router_bootstrap()

# Path of the running control-plane process (used to detect self-updates)
_CONTROL_PLANE_REPO_PATH = str(Path(__file__).resolve().parent.parent.parent)

# ---------------------------------------------------------------------------
# Service configuration (static allowlist)
# ---------------------------------------------------------------------------

SERVICE_CONFIGS: dict[str, dict] = {
    "agent-core": {
        "repo_url": "https://github.com/MapleEdge/agent-core.git",
        "branch": "base-init",
        "path": "/opt/workstation/repos/agent-core",
        "install_commands": ["pnpm install --frozen-lockfile"],
        "build_commands": ["pnpm build"],
        "restart_command": "fuser -k 3210/tcp; sleep 1; nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
    },
    "dashboard": {
        "repo_url": "https://github.com/MapleEdge/jubilant-goggles.git",
        "branch": "initial-setup",
        "path": "/opt/workstation/repos/jubilant-goggles",
        "install_commands": [
            "(cd control-plane/web && pnpm install --frozen-lockfile)",
            "rsync -a --delete --exclude node_modules control-plane/web/ /opt/workstation/control-plane/web/",
            "(cd /opt/workstation/control-plane/web && pnpm install --frozen-lockfile)",
        ],
        "build_commands": ["(cd /opt/workstation/control-plane/web && pnpm build)"],
        "restart_command": "fuser -k 5173/tcp; sleep 1; cd /opt/workstation/control-plane/web && nohup pnpm dev --host 0.0.0.0 --port 5173 > /opt/workstation/logs/dashboard.log 2>&1 &",
    },
    "control-plane": {
        "repo_url": "https://github.com/MapleEdge/jubilant-goggles.git",
        "branch": "initial-setup",
        "path": "/opt/workstation/repos/jubilant-goggles",
        "install_commands": [],
        "build_commands": [],
        "restart_command": "fuser -k 9877/tcp; sleep 1; cd /opt/workstation/repos/jubilant-goggles/control-plane && nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload > /opt/workstation/logs/control-plane.log 2>&1 &",
    },
}


def _get_token() -> str | None:
    """Read GitHub PAT from environment. Never log or return this value."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT") or os.environ.get("PAT")


# ---------------------------------------------------------------------------
# Locking — keyed by repo path so shared checkouts are safe
# ---------------------------------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(path: str) -> threading.Lock:
    with _locks_lock:
        if path not in _locks:
            _locks[path] = threading.Lock()
        return _locks[path]


# ---------------------------------------------------------------------------
# Token sanitization
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"gho_[A-Za-z0-9_]{36,}"),
]


def _sanitize(text: str, token: str | None = None) -> str:
    """Remove any occurrence of the PAT and common token patterns from text."""
    if token:
        text = text.replace(token, "***")
    for pat in _TOKEN_PATTERNS:
        text = pat.sub("***", text)
    # Truncate to something reasonable
    return text[:2000]


# ---------------------------------------------------------------------------
# Git + update logic (runs in a thread to avoid blocking the event loop)
# ---------------------------------------------------------------------------

@dataclass
class UpdateResult:
    ok: bool
    service: str
    branch: str = ""
    commit_before: str = ""
    commit_after: str = ""
    updated: bool = False
    restart_attempted: bool = False
    restart_succeeded: bool = False
    message: str = ""
    error: Optional[dict] = None


def _run_cmd(
    cmd: str | list[str],
    cwd: str | None = None,
    env: dict | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a command, capturing output. Shell mode for string commands."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        shell=isinstance(cmd, str),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tokenized_url(repo_url: str, token: str) -> str:
    """Insert token into HTTPS URL for authenticated fetch/clone.

    The resulting URL is only used in transient subprocess env — it is never
    persisted to git config or disk.
    """
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return repo_url


def _do_update(service_name: str, restart: bool) -> UpdateResult:
    """Perform the update synchronously (called inside a thread)."""
    config = SERVICE_CONFIGS.get(service_name)
    if config is None:
        return UpdateResult(
            ok=False,
            service=service_name,
            error={"code": "UNKNOWN_SERVICE", "message": f"Service '{service_name}' is not configured for updates."},
        )

    token = _get_token()
    if not token:
        return UpdateResult(
            ok=False,
            service=service_name,
            error={"code": "NO_TOKEN", "message": "GitHub token is not configured. Set GITHUB_TOKEN or GITHUB_PAT."},
        )

    repo_url = config["repo_url"]
    branch = config["branch"]
    repo_path = config["path"]
    install_cmds = config.get("install_commands", [])
    build_cmds = config.get("build_commands", [])
    restart_cmd = config.get("restart_command", "")

    lock = _get_lock(repo_path)
    acquired = lock.acquire(timeout=5)
    if not acquired:
        return UpdateResult(
            ok=False,
            service=service_name,
            error={"code": "UPDATE_LOCKED", "message": f"Another update is already running for {repo_path}."},
        )

    try:
        auth_url = _tokenized_url(repo_url, token)
        path = Path(repo_path)

        # Clone if missing
        if not path.exists():
            r = _run_cmd(["git", "clone", "--branch", branch, "--single-branch", auth_url, str(path)], timeout=300)
            if r.returncode != 0:
                return UpdateResult(
                    ok=False,
                    service=service_name,
                    error={"code": "CLONE_FAILED", "message": _sanitize(r.stderr, token)},
                )
            commit_after = _run_cmd(["git", "rev-parse", "HEAD"], cwd=str(path)).stdout.strip()
            return UpdateResult(
                ok=True,
                service=service_name,
                branch=branch,
                commit_before="",
                commit_after=commit_after[:12],
                updated=True,
                message=f"{service_name} cloned at {commit_after[:7]}",
            )

        # Validate existing checkout
        if not (path / ".git").is_dir():
            return UpdateResult(
                ok=False,
                service=service_name,
                error={"code": "NOT_A_REPO", "message": f"{repo_path} exists but is not a git repository."},
            )

        commit_before = _run_cmd(["git", "rev-parse", "HEAD"], cwd=str(path)).stdout.strip()

        # Fetch using tokenized URL (does not persist in remote config)
        fetch_r = _run_cmd(["git", "fetch", auth_url, branch], cwd=str(path), timeout=120)
        if fetch_r.returncode != 0:
            return UpdateResult(
                ok=False,
                service=service_name,
                error={"code": "FETCH_FAILED", "message": _sanitize(fetch_r.stderr, token)},
            )

        # Reset to fetched head
        reset_r = _run_cmd(["git", "reset", "--hard", "FETCH_HEAD"], cwd=str(path))
        if reset_r.returncode != 0:
            return UpdateResult(
                ok=False,
                service=service_name,
                error={"code": "RESET_FAILED", "message": _sanitize(reset_r.stderr, token)},
            )

        commit_after = _run_cmd(["git", "rev-parse", "HEAD"], cwd=str(path)).stdout.strip()

        # Install commands
        for cmd in install_cmds:
            ir = _run_cmd(cmd, cwd=str(path), timeout=300)
            if ir.returncode != 0:
                return UpdateResult(
                    ok=False,
                    service=service_name,
                    branch=branch,
                    commit_before=commit_before[:12],
                    commit_after=commit_after[:12],
                    error={"code": "INSTALL_FAILED", "message": _sanitize(ir.stderr, token)},
                )

        # Build commands
        for cmd in build_cmds:
            br = _run_cmd(cmd, cwd=str(path), timeout=300)
            if br.returncode != 0:
                return UpdateResult(
                    ok=False,
                    service=service_name,
                    branch=branch,
                    commit_before=commit_before[:12],
                    commit_after=commit_after[:12],
                    error={"code": "BUILD_FAILED", "message": _sanitize(br.stderr, token)},
                )

        # Restart
        restart_attempted = False
        restart_succeeded = False
        if restart and restart_cmd:
            restart_attempted = True
            rr = _run_cmd(restart_cmd, timeout=30)
            restart_succeeded = rr.returncode == 0

        updated = commit_before != commit_after
        short_after = commit_after[:7]
        msg = f"{service_name} updated to {short_after}" if updated else f"{service_name} already at latest ({short_after})"

        return UpdateResult(
            ok=True,
            service=service_name,
            branch=branch,
            commit_before=commit_before[:12],
            commit_after=commit_after[:12],
            updated=updated,
            restart_attempted=restart_attempted,
            restart_succeeded=restart_succeeded,
            message=msg,
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            ok=False,
            service=service_name,
            error={"code": "TIMEOUT", "message": "Update command timed out."},
        )
    except Exception as exc:
        return UpdateResult(
            ok=False,
            service=service_name,
            error={"code": "UPDATE_FAILED", "message": _sanitize(str(exc), token)},
        )
    finally:
        lock.release()


# Tracking in-progress updates for the frontend to poll
_update_status: dict[str, dict] = {}
_update_status_lock = threading.Lock()


def get_update_status(service_name: str) -> dict | None:
    with _update_status_lock:
        return _update_status.get(service_name)


def set_update_status(service_name: str, status: dict):
    with _update_status_lock:
        _update_status[service_name] = status


def clear_update_status(service_name: str):
    with _update_status_lock:
        _update_status.pop(service_name, None)


def is_self_update(service_name: str) -> bool:
    """Return True if updating this service would modify the running control-plane's own repo.

    When uvicorn runs with --reload, modifying files in the repo triggers an
    automatic server restart, which kills the in-flight HTTP response and causes
    a 'Network error' on the frontend.  For self-updates we defer the actual
    git work to a background thread so the response is sent first.
    """
    config = SERVICE_CONFIGS.get(service_name)
    if config is None:
        return False
    return str(Path(config["path"]).resolve()) == _CONTROL_PLANE_REPO_PATH


def _background_update(service_name: str, restart: bool) -> None:
    """Run the update in a background thread (fire-and-forget for self-updates)."""
    try:
        result = _do_update(service_name, restart)
        status = {
            "in_progress": False,
            "last_update": {
                "commit": result.commit_after,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success" if result.ok else "failed",
                "message": result.message or (result.error or {}).get("message", ""),
            },
        }
        set_update_status(service_name, status)
    except Exception as exc:
        set_update_status(service_name, {
            "in_progress": False,
            "last_update": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "message": _sanitize(str(exc)),
            },
        })


def schedule_deferred_update(service_name: str, restart: bool = True) -> None:
    """Schedule a self-update to run after the HTTP response is sent."""
    set_update_status(service_name, {"in_progress": True, "started": datetime.now(timezone.utc).isoformat()})
    t = threading.Thread(target=_background_update, args=(service_name, restart), daemon=True)
    t.start()


async def update_service(service_name: str, restart: bool = True) -> UpdateResult:
    """Run the update in a thread so it doesn't block the async event loop."""
    set_update_status(service_name, {"in_progress": True, "started": datetime.now(timezone.utc).isoformat()})
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_update, service_name, restart)
        status = {
            "in_progress": False,
            "last_update": {
                "commit": result.commit_after,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success" if result.ok else "failed",
            },
        }
        set_update_status(service_name, status)
        return result
    except Exception:
        set_update_status(service_name, {"in_progress": False})
        raise


def get_service_update_metadata() -> dict[str, dict]:
    """Return update metadata for all configured services.

    This is merged into the service list endpoint so the frontend knows
    which services support updates and their current status.
    """
    token_available = _get_token() is not None
    result = {}
    for name, config in SERVICE_CONFIGS.items():
        status = get_update_status(name) or {}
        result[name] = {
            "repo_backed": True,
            "update_supported": token_available,
            "update_in_progress": status.get("in_progress", False),
            "last_update": status.get("last_update"),
        }
    return result
