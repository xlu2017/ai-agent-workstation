from __future__ import annotations

import json
import os
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from api.app_automation.adapter_base import AdapterExecution
from api.app_automation.models import AppAction, AppAutomationExecuteRequest
from api.repo_provider import get_repo_provider_token


def _mock_enabled() -> bool:
    return os.environ.get("APP_AUTOMATION_MOCK", "").lower() in {"1", "true", "yes", "on"}


def _json_request(method: str, url: str, headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {"status": response.status}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)[:500]) from exc


def _github_headers() -> dict[str, str]:
    token = get_repo_provider_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jubilant-goggles-app-automation",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def execute_vendor_action(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest) -> AdapterExecution:
    if _mock_enabled():
        return _mock_execution(vendor_id, source_path, action, request)
    if vendor_id == "mcp_servers":
        return _execute_mcp_servers(source_path, action, request)
    if vendor_id == "composio":
        return _execute_http_or_configured(vendor_id, source_path, action, request, "COMPOSIO_PROXY_URL")
    if vendor_id == "activepieces":
        return _execute_http_or_configured(vendor_id, source_path, action, request, "ACTIVEPIECES_WEBHOOK_URL")
    if vendor_id == "n8n":
        return _execute_http_or_configured(vendor_id, source_path, action, request, "N8N_WEBHOOK_URL")
    if vendor_id == "stagehand":
        return _execute_command_or_configured(vendor_id, source_path, action, request, "STAGEHAND_COMMAND")
    if vendor_id == "browser_use":
        return _execute_command_or_configured(vendor_id, source_path, action, request, "BROWSER_USE_COMMAND")
    if vendor_id == "skyvern":
        return _execute_command_or_configured(vendor_id, source_path, action, request, "SKYVERN_COMMAND")
    return AdapterExecution(
        ok=False,
        status="adapter_not_supported",
        message=f"No runtime adapter exists for vendor {vendor_id}.",
        error={"code": "ADAPTER_NOT_SUPPORTED", "message": f"No runtime adapter exists for vendor {vendor_id}."},
    )


def _mock_execution(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest) -> AdapterExecution:
    return AdapterExecution(
        ok=True,
        status="completed",
        message=f"Mock app automation completed for {action.id} through {vendor_id}.",
        planned_steps=[
            f"Confirmed vendored source path: {source_path}.",
            f"Simulated {action.execution_kind} execution for {action.id}.",
            "Returned normalized app automation result without external side effects.",
        ],
        result={
            "mock": True,
            "vendor": vendor_id,
            "app_id": action.app_id,
            "action_id": action.id,
            "params": request.params,
        },
    )


def _execute_mcp_servers(source_path: Path, action: AppAction, request: AppAutomationExecuteRequest) -> AdapterExecution:
    if action.id == "github.search_repo":
        return _github_search_repo(source_path, request)
    if action.id == "github.create_issue":
        return _github_create_issue(source_path, request)
    return AdapterExecution(
        ok=False,
        status="action_not_supported_by_adapter",
        message=f"Vendored MCP reference adapter does not yet implement {action.id}.",
        planned_steps=["MCP source is present.", "Implement process/client transport for this tool before live use."],
        error={"code": "ACTION_NOT_SUPPORTED_BY_ADAPTER", "message": f"MCP adapter does not implement {action.id}."},
    )


def _github_search_repo(source_path: Path, request: AppAutomationExecuteRequest) -> AdapterExecution:
    repo = str(request.params.get("repo", "")).strip()
    query = str(request.params.get("query", "")).strip()
    kind = str(request.params.get("kind", "code")).strip() or "code"
    if not repo or not query:
        return AdapterExecution(False, "invalid_params", "repo and query are required.", error={"code": "INVALID_PARAMS", "message": "repo and query are required."})
    if kind not in {"code", "issues"}:
        kind = "code"
    if kind == "issues":
        q = urllib.parse.urlencode({"q": f"repo:{repo} {query}"})
        url = f"https://api.github.com/search/issues?{q}"
    else:
        q = urllib.parse.urlencode({"q": f"{query} repo:{repo}"})
        url = f"https://api.github.com/search/code?{q}"
    try:
        data = _json_request("GET", url, headers=_github_headers())
    except RuntimeError as exc:
        return AdapterExecution(
            ok=False,
            status="runtime_error",
            message=f"GitHub search failed: {exc}",
            planned_steps=["Use vendored MCP GitHub reference as the protocol source.", "Execute read-only GitHub Search API through server-side repo provider auth."],
            error={"code": "GITHUB_SEARCH_FAILED", "message": str(exc)},
        )
    items = data.get("items", []) if isinstance(data, dict) else []
    simplified = []
    for item in items[:10]:
        simplified.append({
            "name": item.get("name") or item.get("title"),
            "path": item.get("path"),
            "html_url": item.get("html_url"),
            "repository": (item.get("repository") or {}).get("full_name"),
        })
    return AdapterExecution(
        ok=True,
        status="completed",
        message=f"GitHub {kind} search completed through MCP/GitHub adapter.",
        planned_steps=[
            f"Loaded vendored MCP source from {source_path}.",
            "Used platform-owned GitHub REST execution for the read-only search action.",
        ],
        result={"kind": kind, "repo": repo, "query": query, "total_count": data.get("total_count"), "items": simplified},
    )


def _github_create_issue(source_path: Path, request: AppAutomationExecuteRequest) -> AdapterExecution:
    repo = str(request.params.get("repo", "")).strip()
    title = str(request.params.get("title", "")).strip()
    body = str(request.params.get("body", ""))
    if not repo or not title:
        return AdapterExecution(False, "invalid_params", "repo and title are required.", error={"code": "INVALID_PARAMS", "message": "repo and title are required."})
    token = get_repo_provider_token()
    if not token:
        return AdapterExecution(False, "runtime_not_configured", "GitHub auth is not configured on the server.", error={"code": "GITHUB_AUTH_REQUIRED", "message": "Configure GitHub auth before creating issues."})
    try:
        data = _json_request("POST", f"https://api.github.com/repos/{repo}/issues", headers={**_github_headers(), "Content-Type": "application/json"}, payload={"title": title, "body": body})
    except RuntimeError as exc:
        return AdapterExecution(False, "runtime_error", f"GitHub issue creation failed: {exc}", error={"code": "GITHUB_CREATE_ISSUE_FAILED", "message": str(exc)})
    return AdapterExecution(
        ok=True,
        status="completed",
        message="GitHub issue created through MCP/GitHub adapter.",
        planned_steps=[f"Loaded vendored MCP source from {source_path}.", "Used platform-owned GitHub REST execution after approval gate."],
        result={"repo": repo, "issue_number": data.get("number"), "html_url": data.get("html_url"), "title": data.get("title")},
    )


def _execute_http_or_configured(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest, env_name: str) -> AdapterExecution:
    url = os.environ.get(env_name)
    if not url:
        return AdapterExecution(
            ok=False,
            status="runtime_not_configured",
            message=f"{vendor_id} source is vendored, but {env_name} is not configured for live execution.",
            planned_steps=[
                f"Loaded vendored source from {source_path}.",
                f"Set {env_name} to enable live {vendor_id} execution through a controlled endpoint.",
            ],
            error={"code": "RUNTIME_NOT_CONFIGURED", "message": f"Set {env_name} to enable live execution."},
        )
    payload = {"app_id": action.app_id, "action_id": action.id, "params": request.params, "session_id": request.session_id}
    try:
        data = _json_request("POST", url, headers={"Content-Type": "application/json"}, payload=payload)
    except RuntimeError as exc:
        return AdapterExecution(False, "runtime_error", f"{vendor_id} execution failed: {exc}", error={"code": "VENDOR_HTTP_FAILED", "message": str(exc)})
    return AdapterExecution(
        ok=True,
        status="completed",
        message=f"{vendor_id} action completed through configured endpoint.",
        planned_steps=[f"Loaded vendored source from {source_path}.", f"Posted normalized action envelope to {env_name}."],
        result={"vendor_response": data},
    )


def _execute_command_or_configured(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest, env_name: str) -> AdapterExecution:
    command = os.environ.get(env_name)
    if not command:
        return AdapterExecution(
            ok=False,
            status="runtime_not_configured",
            message=f"{vendor_id} source is vendored, but {env_name} is not configured for live execution.",
            planned_steps=[
                f"Loaded vendored source from {source_path}.",
                f"Set {env_name} to a controlled command that accepts a JSON envelope on stdin.",
            ],
            error={"code": "RUNTIME_NOT_CONFIGURED", "message": f"Set {env_name} to enable live execution."},
        )
    envelope = json.dumps({"app_id": action.app_id, "action_id": action.id, "params": request.params, "session_id": request.session_id})
    try:
        result = subprocess.run(shlex.split(command), input=envelope, capture_output=True, text=True, timeout=120, cwd=source_path)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return AdapterExecution(False, "runtime_error", f"{vendor_id} command failed: {exc}", error={"code": "VENDOR_COMMAND_FAILED", "message": str(exc)[:500]})
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "command failed")[-1000:]
        return AdapterExecution(False, "runtime_error", f"{vendor_id} command failed: {message}", error={"code": "VENDOR_COMMAND_FAILED", "message": message})
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else {"stdout": ""}
    except json.JSONDecodeError:
        parsed = {"stdout": result.stdout[-4000:]}
    return AdapterExecution(
        ok=True,
        status="completed",
        message=f"{vendor_id} action completed through configured command.",
        planned_steps=[f"Loaded vendored source from {source_path}.", f"Ran controlled command from {env_name}."],
        result={"vendor_response": parsed},
    )
