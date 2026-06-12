"""Read-only latest-check API for repo-backed services."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from api.service_updater import (
    SERVICE_CONFIGS,
    _get_lock,
    _get_token,
    _git_commit,
    _now,
    _resolve_branch,
    _run_cmd,
    _sanitize,
    _tokenized_url,
)

router = APIRouter(prefix="/api/v2/services", tags=["service-updates"])

UpdateCheckStatus = Literal[
    "up_to_date",
    "update_available",
    "missing_checkout",
    "invalid_checkout",
    "token_missing",
    "branch_resolve_failed",
    "remote_check_failed",
    "local_commit_missing",
    "update_locked",
]


def _remote_commit(repo_url: str, branch: str, token: str) -> tuple[str, str | None]:
    auth_url = _tokenized_url(repo_url, token)
    result = _run_cmd(["git", "ls-remote", auth_url, f"refs/heads/{branch}"], timeout=60)
    if result.returncode != 0:
        return "", _sanitize(result.stderr or result.stdout, token)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == f"refs/heads/{branch}":
            return parts[0], None
    return "", f"Remote branch '{branch}' was not found."


def _response(
    *,
    service_name: str,
    status: UpdateCheckStatus,
    branch: str = "",
    local_commit: str = "",
    remote_commit: str = "",
    update_available: bool = False,
    message: str,
    ok: bool = True,
    error: dict | None = None,
) -> dict[str, object]:
    return {
        "ok": ok,
        "service": service_name,
        "status": status,
        "branch": branch,
        "local_commit": local_commit[:12],
        "remote_commit": remote_commit[:12],
        "update_available": update_available,
        "checked_at": _now(),
        "message": message,
        "error": error,
    }


def check_service_latest(service_name: str) -> dict[str, object]:
    """Return read-only local-vs-remote freshness for a repo-backed service."""
    config = SERVICE_CONFIGS.get(service_name)
    if config is None:
        raise HTTPException(
            404,
            {
                "ok": False,
                "service": service_name,
                "status": "unknown_service",
                "error": {
                    "code": "UNKNOWN_SERVICE",
                    "message": f"Service '{service_name}' is not configured for repo-backed updates.",
                },
            },
        )

    token = _get_token()
    if not token:
        return _response(
            service_name=service_name,
            status="token_missing",
            ok=False,
            message="GitHub token is not configured. Set GITHUB_TOKEN or GITHUB_PAT.",
            error={"code": "NO_TOKEN", "message": "GitHub token is not configured."},
        )

    repo_url = config["repo_url"]
    repo_path = config["path"]
    branch, branch_error = _resolve_branch(repo_url, config.get("branch"), token)
    if branch_error or not branch:
        return _response(
            service_name=service_name,
            status="branch_resolve_failed",
            ok=False,
            message=branch_error or "Unable to resolve repository default branch.",
            error={"code": "BRANCH_RESOLVE_FAILED", "message": branch_error or "Unable to resolve repository default branch."},
        )

    remote, remote_error = _remote_commit(repo_url, branch, token)
    if remote_error or not remote:
        return _response(
            service_name=service_name,
            status="remote_check_failed",
            branch=branch,
            ok=False,
            message=remote_error or "Unable to read remote branch commit.",
            error={"code": "REMOTE_CHECK_FAILED", "message": remote_error or "Unable to read remote branch commit."},
        )

    lock = _get_lock(repo_path)
    acquired = lock.acquire(timeout=0.1)
    if not acquired:
        return _response(
            service_name=service_name,
            status="update_locked",
            branch=branch,
            remote_commit=remote,
            ok=False,
            message=f"Another update is already running for {repo_path}.",
            error={"code": "UPDATE_LOCKED", "message": f"Another update is already running for {repo_path}."},
        )

    try:
        path = Path(repo_path)
        if not path.exists():
            return _response(
                service_name=service_name,
                status="missing_checkout",
                branch=branch,
                remote_commit=remote,
                update_available=True,
                message=f"{service_name} is not cloned locally. Update Latest will clone {branch} at {remote[:7]}.",
            )

        if not (path / ".git").is_dir():
            return _response(
                service_name=service_name,
                status="invalid_checkout",
                branch=branch,
                remote_commit=remote,
                ok=False,
                message=f"{repo_path} exists but is not a git repository.",
                error={"code": "NOT_A_REPO", "message": f"{repo_path} exists but is not a git repository."},
            )

        local = _git_commit(path)
        if not local:
            return _response(
                service_name=service_name,
                status="local_commit_missing",
                branch=branch,
                remote_commit=remote,
                ok=False,
                message=f"Unable to read the local commit for {service_name}.",
                error={"code": "LOCAL_COMMIT_MISSING", "message": f"Unable to read the local commit for {service_name}."},
            )

        if local == remote:
            return _response(
                service_name=service_name,
                status="up_to_date",
                branch=branch,
                local_commit=local,
                remote_commit=remote,
                update_available=False,
                message=f"{service_name} is up to date at {local[:7]}.",
            )

        return _response(
            service_name=service_name,
            status="update_available",
            branch=branch,
            local_commit=local,
            remote_commit=remote,
            update_available=True,
            message=f"Update available for {service_name}: {local[:7]} → {remote[:7]}.",
        )
    except subprocess.TimeoutExpired:
        return _response(
            service_name=service_name,
            status="remote_check_failed",
            branch=branch,
            remote_commit=remote,
            ok=False,
            message="Update check timed out.",
            error={"code": "TIMEOUT", "message": "Update check timed out."},
        )
    except Exception as exc:
        return _response(
            service_name=service_name,
            status="remote_check_failed",
            branch=branch,
            remote_commit=remote,
            ok=False,
            message=_sanitize(str(exc), token),
            error={"code": "UPDATE_CHECK_FAILED", "message": _sanitize(str(exc), token)},
        )
    finally:
        lock.release()


@router.get("/{service_name}/update-check")
def service_update_check(service_name: str) -> dict[str, object]:
    """Check whether Update Latest would change a repo-backed service."""
    return check_service_latest(service_name)
