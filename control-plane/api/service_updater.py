"""
Server-side GitHub update logic for repo-backed services.

This module powers the dashboard's "Update latest" action. It is intentionally
server-side: the browser never receives the personal access token used for
private GitHub fetches.

Security and correctness rules:
- The PAT is read from GITHUB_TOKEN, GITHUB_PAT, or PAT and is never returned.
- GitHub tokens are injected only into transient fetch/clone URLs.
- Command output is sanitized before it is surfaced to the UI.
- A per-repo-path lock prevents concurrent updates to shared checkouts.
- Update status is persisted to disk so self-updates survive uvicorn reloads.
- Missing checkouts are cloned and then still run install/build/restart steps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _install_session_architecture_router_bootstrap() -> None:
    """Mount the session architecture router from the existing server import path."""
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

CONTROL_PLANE_ROOT = Path(__file__).resolve().parent.parent
_CONTROL_PLANE_REPO_PATH = str(CONTROL_PLANE_ROOT.parent.resolve())
UPDATE_STATUS_PATH = Path(os.environ.get("SERVICE_UPDATE_STATUS_PATH", "/opt/workstation/logs/service-updates.json"))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


# ---------------------------------------------------------------------------
# Service configuration (static allowlist)
# ---------------------------------------------------------------------------

SERVICE_CONFIGS: dict[str, dict] = {
    "agent-core": {
        "repo_url": _env("AGENT_CORE_REPO_URL", "https://github.com/xlu2017/agent-core.git"),
        "branch": _env("AGENT_CORE_UPDATE_BRANCH"),
        "path": _env("AGENT_CORE_REPO_PATH", "/opt/workstation/repos/agent-core"),
        "install_commands": ["pnpm install --frozen-lockfile"],
        "build_commands": ["pnpm build"],
        "restart_command": "fuser -k 3210/tcp; sleep 1; cd /opt/workstation/repos/agent-core && nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
    },
    "dashboard": {
        "repo_url": _env("JUBILANT_GOGGLES_REPO_URL", "https://github.com/xlu2017/jubilant-goggles.git"),
        "branch": _env("JUBILANT_GOGGLES_UPDATE_BRANCH"),
        "path": _env("JUBILANT_GOGGLES_REPO_PATH", "/opt/workstation/repos/jubilant-goggles"),
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
        "repo_url": _env("JUBILANT_GOGGLES_REPO_URL", "https://github.com/xlu2017/jubilant-goggles.git"),
        "branch": _env("JUBILANT_GOGGLES_UPDATE_BRANCH"),
        "path": _env("JUBILANT_GOGGLES_REPO_PATH", "/opt/workstation/repos/jubilant-goggles"),
        "install_commands": ["pnpm install --frozen-lockfile"],
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
_update_status: dict[str, dict] = {}
_update_status_lock = threading.Lock()


def _get_lock(path: str) -> threading.Lock:
    with _locks_lock:
        if path not in _locks:
            _locks[path] = threading.Lock()
        return _locks[path]


# ---------------------------------------------------------------------------
# Token sanitization
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gho_[A-Za-z0-9_]{20,}"),
    re.compile(r"x-access-token:[^@\s]+@"),
]


def _sanitize(text: str, token: str | None = None) -> str:
    if token:
        text = text.replace(token, "***")
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("***", text)
    return text[:2500]


# ---------------------------------------------------------------------------
# Status persistence
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_persisted_status() -> dict[str, dict]:
    try:
        if not UPDATE_STATUS_PATH.exists():
            return {}
        raw = json.loads(UPDATE_STATUS_PATH.read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _persist_status_unlocked() -> None:
    try:
        UPDATE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {**_load_persisted_status(), **_update_status}
        tmp = UPDATE_STATUS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tmp.replace(UPDATE_STATUS_PATH)
    except Exception as exc:  # pragma: no cover - status should not fail update
        logger.warning("Unable to persist service update status: %s", exc)


def get_update_status(service_name: str) -> dict | None:
    with _update_status_lock:
        if service_name in _update_status:
            return _update_status[service_name]
    return _load_persisted_status().get(service_name)


def set_update_status(service_name: str, status: dict) -> None:
    status = {**status, "updated_at": _now()}
    with _update_status_lock:
        _update_status[service_name] = status
        _persist_status_unlocked()


def clear_update_status(service_name: str) -> None:
    with _update_status_lock:
        _update_status.pop(service_name, None)
        persisted = _load_persisted_status()
        persisted.pop(service_name, None)
        try:
            UPDATE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            UPDATE_STATUS_PATH.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Git + update logic
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
    deferred: bool = False
    message: str = ""
    error: Optional[dict] = None
    steps: list[dict] | None = None


def _run_cmd(
    cmd: str | list[str],
    cwd: str | None = None,
    env: dict | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    command_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=command_env,
        shell=isinstance(cmd, str),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tokenized_url(repo_url: str, token: str) -> str:
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return repo_url


def _resolve_branch(repo_url: str, configured_branch: str | None, token: str) -> tuple[str | None, str | None]:
    if configured_branch:
        return configured_branch, None
    auth_url = _tokenized_url(repo_url, token)
    result = _run_cmd(["git", "ls-remote", "--symref", auth_url, "HEAD"], timeout=60)
    if result.returncode != 0:
        return None, _sanitize(result.stderr or result.stdout, token)
    for line in result.stdout.splitlines():
        if line.startswith("ref:") and "HEAD" in line:
            ref = line.split()[1]
            if ref.startswith("refs/heads/"):
                return ref.removeprefix("refs/heads/"), None
    return "main", None


def _git_commit(path: Path) -> str:
    result = _run_cmd(["git", "rev-parse", "HEAD"], cwd=str(path))
    return result.stdout.strip() if result.returncode == 0 else ""


def _run_steps(commands: list[str], cwd: str, token: str | None, phase: str, steps: list[dict]) -> tuple[bool, dict | None]:
    for command in commands:
        started = time.time()
        result = _run_cmd(command, cwd=cwd, timeout=600)
        duration_ms = int((time.time() - started) * 1000)
        step = {
            "phase": phase,
            "command": _sanitize(command, token),
            "ok": result.returncode == 0,
            "duration_ms": duration_ms,
            "stdout": _sanitize(result.stdout, token),
            "stderr": _sanitize(result.stderr, token),
        }
        steps.append(step)
        if result.returncode != 0:
            return False, {"code": f"{phase.upper()}_FAILED", "message": step["stderr"] or step["stdout"] or f"{phase} failed"}
    return True, None


def _do_update(service_name: str, restart: bool) -> UpdateResult:
    config = SERVICE_CONFIGS.get(service_name)
    if config is None:
        return UpdateResult(False, service_name, error={"code": "UNKNOWN_SERVICE", "message": f"Service '{service_name}' is not configured for updates."})

    token = _get_token()
    if not token:
        return UpdateResult(False, service_name, error={"code": "NO_TOKEN", "message": "GitHub token is not configured. Set GITHUB_TOKEN or GITHUB_PAT."})

    repo_url = config["repo_url"]
    repo_path = config["path"]
    branch, branch_error = _resolve_branch(repo_url, config.get("branch"), token)
    if branch_error or not branch:
        return UpdateResult(False, service_name, error={"code": "BRANCH_RESOLVE_FAILED", "message": branch_error or "Unable to resolve repository default branch."})

    install_cmds = config.get("install_commands", [])
    build_cmds = config.get("build_commands", [])
    restart_cmd = config.get("restart_command", "")
    steps: list[dict] = []

    lock = _get_lock(repo_path)
    acquired = lock.acquire(timeout=5)
    if not acquired:
        return UpdateResult(False, service_name, branch=branch, error={"code": "UPDATE_LOCKED", "message": f"Another update is already running for {repo_path}."})

    try:
        auth_url = _tokenized_url(repo_url, token)
        path = Path(repo_path)
        commit_before = ""

        if not path.exists():
            clone = _run_cmd(["git", "clone", "--branch", branch, "--single-branch", auth_url, str(path)], timeout=600)
            steps.append({"phase": "clone", "ok": clone.returncode == 0, "stdout": _sanitize(clone.stdout, token), "stderr": _sanitize(clone.stderr, token)})
            if clone.returncode != 0:
                return UpdateResult(False, service_name, branch=branch, steps=steps, error={"code": "CLONE_FAILED", "message": _sanitize(clone.stderr or clone.stdout, token)})
        else:
            if not (path / ".git").is_dir():
                return UpdateResult(False, service_name, branch=branch, error={"code": "NOT_A_REPO", "message": f"{repo_path} exists but is not a git repository."})
            commit_before = _git_commit(path)
            fetch = _run_cmd(["git", "fetch", "--prune", auth_url, branch], cwd=str(path), timeout=180)
            steps.append({"phase": "fetch", "ok": fetch.returncode == 0, "stdout": _sanitize(fetch.stdout, token), "stderr": _sanitize(fetch.stderr, token)})
            if fetch.returncode != 0:
                return UpdateResult(False, service_name, branch=branch, commit_before=commit_before[:12], steps=steps, error={"code": "FETCH_FAILED", "message": _sanitize(fetch.stderr or fetch.stdout, token)})
            reset = _run_cmd(["git", "reset", "--hard", "FETCH_HEAD"], cwd=str(path), timeout=120)
            steps.append({"phase": "reset", "ok": reset.returncode == 0, "stdout": _sanitize(reset.stdout, token), "stderr": _sanitize(reset.stderr, token)})
            if reset.returncode != 0:
                return UpdateResult(False, service_name, branch=branch, commit_before=commit_before[:12], steps=steps, error={"code": "RESET_FAILED", "message": _sanitize(reset.stderr or reset.stdout, token)})

        commit_after = _git_commit(path)

        ok, error = _run_steps(install_cmds, str(path), token, "install", steps)
        if not ok:
            return UpdateResult(False, service_name, branch=branch, commit_before=commit_before[:12], commit_after=commit_after[:12], steps=steps, error=error)

        ok, error = _run_steps(build_cmds, str(path), token, "build", steps)
        if not ok:
            return UpdateResult(False, service_name, branch=branch, commit_before=commit_before[:12], commit_after=commit_after[:12], steps=steps, error=error)

        restart_attempted = False
        restart_succeeded = False
        if restart and restart_cmd:
            restart_attempted = True
            restart_result = _run_cmd(restart_cmd, timeout=45)
            restart_succeeded = restart_result.returncode == 0
            steps.append({"phase": "restart", "ok": restart_succeeded, "stdout": _sanitize(restart_result.stdout, token), "stderr": _sanitize(restart_result.stderr, token)})

        updated = bool(commit_after and commit_before != commit_after)
        short_after = commit_after[:7] if commit_after else "unknown"
        message = f"{service_name} updated to {short_after}" if updated else f"{service_name} already at latest ({short_after})"
        if restart_attempted and not restart_succeeded:
            message += "; restart command did not report success"

        return UpdateResult(
            ok=True,
            service=service_name,
            branch=branch,
            commit_before=commit_before[:12],
            commit_after=commit_after[:12],
            updated=updated,
            restart_attempted=restart_attempted,
            restart_succeeded=restart_succeeded,
            message=message,
            steps=steps,
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(False, service_name, branch=branch, steps=steps, error={"code": "TIMEOUT", "message": "Update command timed out."})
    except Exception as exc:
        return UpdateResult(False, service_name, branch=branch, steps=steps, error={"code": "UPDATE_FAILED", "message": _sanitize(str(exc), token)})
    finally:
        lock.release()


def _status_from_result(result: UpdateResult) -> dict:
    return {
        "in_progress": False,
        "last_update": {
            "commit": result.commit_after,
            "branch": result.branch,
            "timestamp": _now(),
            "status": "success" if result.ok else "failed",
            "updated": result.updated,
            "restart_attempted": result.restart_attempted,
            "restart_succeeded": result.restart_succeeded,
            "message": result.message or (result.error or {}).get("message", ""),
            "error": result.error,
            "steps": result.steps or [],
        },
    }


def is_self_update(service_name: str) -> bool:
    config = SERVICE_CONFIGS.get(service_name)
    if config is None:
        return False
    try:
        return str(Path(config["path"]).resolve()) == _CONTROL_PLANE_REPO_PATH
    except Exception:
        return False


def _background_update(service_name: str, restart: bool) -> None:
    try:
        result = _do_update(service_name, restart)
        set_update_status(service_name, _status_from_result(result))
    except Exception as exc:
        set_update_status(service_name, {
            "in_progress": False,
            "last_update": {"timestamp": _now(), "status": "failed", "message": _sanitize(str(exc))},
        })


def schedule_deferred_update(service_name: str, restart: bool = True) -> None:
    status = get_update_status(service_name) or {}
    if status.get("in_progress"):
        return
    set_update_status(service_name, {"in_progress": True, "started": _now(), "message": "Update scheduled."})
    thread = threading.Thread(target=_background_update, args=(service_name, restart), daemon=True)
    thread.start()


async def update_service(service_name: str, restart: bool = True) -> UpdateResult:
    status = get_update_status(service_name) or {}
    if status.get("in_progress"):
        return UpdateResult(False, service_name, error={"code": "UPDATE_LOCKED", "message": f"Another update is already running for {service_name}."})
    set_update_status(service_name, {"in_progress": True, "started": _now(), "message": "Update running."})
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_update, service_name, restart)
        set_update_status(service_name, _status_from_result(result))
        return result
    except Exception:
        set_update_status(service_name, {"in_progress": False})
        raise


def get_service_update_metadata() -> dict[str, dict]:
    token_available = _get_token() is not None
    result = {}
    for name, config in SERVICE_CONFIGS.items():
        status = get_update_status(name) or {}
        result[name] = {
            "repo_backed": True,
            "repo_url": config.get("repo_url"),
            "branch": config.get("branch") or "default",
            "path": config.get("path"),
            "update_supported": token_available,
            "update_in_progress": status.get("in_progress", False),
            "update_message": status.get("message"),
            "last_update": status.get("last_update"),
        }
    return result


def update_result_to_dict(result: UpdateResult) -> dict:
    return asdict(result)
