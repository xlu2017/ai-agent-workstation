"""Repository provider selection and GitHub OAuth routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api import service_updater
from api.repo_provider import (
    RepoProvider,
    build_github_login_url,
    complete_github_login,
    disconnect_github_login,
    get_repo_provider_status,
    get_repo_provider_token,
    list_accessible_repositories,
    select_repo_provider,
)

# Keep the existing service updater code path intact while changing the token
# source to the selected repo provider.
service_updater._get_token = get_repo_provider_token  # type: ignore[attr-defined]

router = APIRouter(prefix="/api/repo-provider", tags=["repo-provider"])


class SelectProviderBody(BaseModel):
    provider: RepoProvider


class LoginUrlResponse(BaseModel):
    ok: bool
    login_url: str | None = None
    state: str | None = None
    error: dict | None = None


def _default_redirect_uri(request: Request) -> str:
    return str(request.url_for("repo_provider_github_callback"))


@router.get("/status")
def repo_provider_status() -> dict:
    """Return provider choices and selected credential status without secrets."""
    return get_repo_provider_status()


@router.get("/repositories")
def repo_provider_repositories(limit: int = 100) -> dict:
    """Return repositories visible to the selected GitHub credential."""
    return list_accessible_repositories(limit=limit)


@router.post("/select")
def repo_provider_select(body: SelectProviderBody) -> dict:
    """Select the repo credential provider used by update/check operations."""
    return select_repo_provider(body.provider)


@router.get("/github/login-url", response_model=LoginUrlResponse)
def github_login_url(request: Request, redirect_uri: str | None = None) -> dict:
    """Build a GitHub OAuth authorization URL for the browser."""
    return build_github_login_url(redirect_uri or _default_redirect_uri(request))


@router.get("/github/callback", name="repo_provider_github_callback")
def github_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> HTMLResponse:
    """Complete GitHub OAuth and return a small browser handoff page."""
    if error:
        result = {"ok": False, "error": {"code": "GITHUB_OAUTH_ERROR", "message": error}}
    elif not code or not state:
        result = {"ok": False, "error": {"code": "MISSING_CALLBACK_PARAMS", "message": "GitHub callback did not include code and state."}}
    else:
        result = complete_github_login(code, state, _default_redirect_uri(request))

    ok = bool(result.get("ok"))
    message = "GitHub login connected. You can close this tab." if ok else str((result.get("error") or {}).get("message", "GitHub login failed."))
    status = "connected" if ok else "failed"
    html = f"""
<!doctype html>
<html>
  <head><title>GitHub login {status}</title></head>
  <body style="font-family: system-ui, sans-serif; padding: 32px;">
    <h1>GitHub login {status}</h1>
    <p>{message}</p>
    <script>
      try {{ localStorage.setItem('repo-provider-oauth-result', JSON.stringify({{"ok": {str(ok).lower()}, "message": {message!r}}})); }} catch (_err) {{}}
      setTimeout(() => {{ window.location.href = '/'; }}, 1200);
    </script>
  </body>
</html>
"""
    return HTMLResponse(html, status_code=200 if ok else 400)


@router.post("/github/disconnect")
def github_disconnect() -> dict:
    """Remove the stored GitHub OAuth token and return updated status."""
    return disconnect_github_login()


@router.get("/token-source")
def repo_provider_token_source() -> dict:
    """Debug-safe token availability endpoint. It never returns a token."""
    status = get_repo_provider_status()
    return {
        "active_provider": status["active_provider"],
        "effective_token_available": status["effective_token_available"],
    }
