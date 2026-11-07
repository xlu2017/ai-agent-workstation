from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from api.app_automation.adapter_base import AdapterExecution
from api.app_automation.config import get_runtime_value
from api.app_automation.models import AppAction, AppAutomationExecuteRequest
from api.repo_provider import get_repo_provider_token

LOCAL_ADAPTER_FILENAME = "jubilant_goggles_adapter.py"


def _mock_enabled() -> bool:
    return os.environ.get("APP_AUTOMATION_MOCK", "").lower() in {"1", "true", "yes", "on"}


def _local_vendor_adapters_enabled() -> bool:
    return os.environ.get("APP_AUTOMATION_LOCAL_VENDOR_ADAPTERS", "true").lower() not in {"0", "false", "no", "off"}


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
        "User-Agent": "ai-agent-workstation-app-automation",
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
    repository_provider = str(request.params.get("repository_provider") or "github").strip() or "github"
    issue_provider = str(request.params.get("issue_provider") or "github").strip() or "github"
    if action.id in {"github.search_repo", "repository.search"} and repository_provider == "github":
        return _github_search_repo(source_path, request)
    if action.id in {"github.create_issue", "issue.create"} and issue_provider == "github":
        return _github_create_issue(source_path, request)
    return _execute_local_vendor_adapter(
        "mcp_servers",
        source_path,
        action,
        request,
        missing_message=f"Vendored MCP reference adapter does not yet implement {action.id} for the requested provider.",
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
    body = str(request.params.get("body", "")) or str(request.params.get("description", ""))
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
    url = os.environ.get(env_name) or get_runtime_value(vendor_id)
    if not url:
        return _execute_local_vendor_adapter(
            vendor_id,
            source_path,
            action,
            request,
            missing_message=f"{vendor_id} source is vendored, but {env_name} is not configured for live external execution.",
            missing_env=env_name,
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
        planned_steps=[f"Loaded vendored source from {source_path}.", f"Posted provider-neutral action envelope to configured {vendor_id} endpoint."],
        result={"vendor_response": data},
    )


def _execute_command_or_configured(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest, env_name: str) -> AdapterExecution:
    command = os.environ.get(env_name) or get_runtime_value(vendor_id)
    if not command:
        return _execute_local_vendor_adapter(
            vendor_id,
            source_path,
            action,
            request,
            missing_message=f"{vendor_id} source is vendored, but {env_name} is not configured for live external execution.",
            missing_env=env_name,
        )
    return _execute_command(vendor_id, source_path, action, request, command, planned_note=f"Ran configured {vendor_id} command.")


def _execute_local_vendor_adapter(
    vendor_id: str,
    source_path: Path,
    action: AppAction,
    request: AppAutomationExecuteRequest,
    missing_message: str,
    missing_env: str | None = None,
) -> AdapterExecution:
    adapter_path = source_path / LOCAL_ADAPTER_FILENAME
    if _local_vendor_adapters_enabled() and adapter_path.exists():
        return _execute_command(
            vendor_id,
            source_path,
            action,
            request,
            f"{shlex.quote(sys.executable)} {shlex.quote(str(adapter_path))}",
            planned_note=f"Ran vendored local adapter {LOCAL_ADAPTER_FILENAME}.",
        )

    planned_steps = [f"Loaded vendored source from {source_path}."]
    if missing_env:
        planned_steps.append(f"Set {missing_env} or add {LOCAL_ADAPTER_FILENAME} to enable non-dry-run adapter dispatch.")
    else:
        planned_steps.append(f"Add {LOCAL_ADAPTER_FILENAME} to enable non-dry-run adapter dispatch.")
    return AdapterExecution(
        ok=False,
        status="runtime_not_configured",
        message=missing_message,
        planned_steps=planned_steps,
        error={"code": "RUNTIME_NOT_CONFIGURED", "message": missing_message},
    )


def _execute_command(vendor_id: str, source_path: Path, action: AppAction, request: AppAutomationExecuteRequest, command: str, planned_note: str) -> AdapterExecution:
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

    if isinstance(parsed, dict) and {"ok", "status", "message"}.issubset(parsed):
        return AdapterExecution(
            ok=bool(parsed.get("ok")),
            status=str(parsed.get("status")),
            message=str(parsed.get("message")),
            planned_steps=[f"Loaded vendored source from {source_path}.", planned_note, *parsed.get("planned_steps", [])],
            result=parsed.get("result") if isinstance(parsed.get("result"), dict) else {"vendor_response": parsed},
            error=parsed.get("error") if isinstance(parsed.get("error"), dict) else None,
        )

    return AdapterExecution(
        ok=True,
        status="completed",
        message=f"{vendor_id} action completed through configured command.",
        planned_steps=[f"Loaded vendored source from {source_path}.", planned_note],
        result={"vendor_response": parsed},
    )
