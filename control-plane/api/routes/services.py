"""Service management routes (list, start, stop, restart, update, repo sources)."""

import os
import subprocess as sp
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.repo_source_registry import (
    get_repo_source,
    list_repo_sources,
    reset_repo_source,
    update_repo_source,
)
from api.service_updater import (
    SERVICE_CONFIGS,
    get_service_update_metadata,
    is_self_update,
    schedule_deferred_update,
    update_service,
)
from api.services.process_control import (
    service_commands,
    start_service_process,
    stop_service_process,
)

router = APIRouter(tags=["services"])


class UpdateLatestBody(BaseModel):
    restart: bool = True


class RepoSourcePatch(BaseModel):
    enabled: bool | None = None
    repo_provider: str | None = Field(default=None, description="Source host provider such as github.")
    owner: str | None = None
    repo: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    path: str | None = None
    install_commands: list[str] | None = None
    build_commands: list[str] | None = None
    restart_command: str | None = None

    def patch(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


@router.get("/api/services")
def list_services():
    services = [
        {"name": "agent-core", "port": 3210, "description": "Advisory memory/planning", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "litellm", "port": 4000, "description": "LLM proxy gateway", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "control-plane", "port": 9877, "description": "FastAPI orchestrator", "can_start": True, "can_stop": False, "can_restart": True},
        {"name": "vendor-runtime", "port": 3000, "description": "Vendor execution runtime (Docker)", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "dashboard", "port": 5173, "description": "Web UI (Vite dev)", "can_start": True, "can_stop": True, "can_restart": True},
    ]
    try:
        result = sp.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        lines = result.stdout
    except Exception:
        lines = ""
    for svc in services:
        port_str = f":{svc['port']}"
        listening = port_str in lines
        svc["status"] = "running" if listening else "stopped"
        svc["pid"] = None
        if listening:
            for line in lines.split("\n"):
                if port_str in line and "pid=" in line:
                    try:
                        pid_part = line.split("pid=")[1].split(",")[0]
                        svc["pid"] = int(pid_part)
                    except (IndexError, ValueError):
                        pass
                    break
    try:
        dr = sp.run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                    capture_output=True, text=True, timeout=5)
        if "vendor-runtime" in dr.stdout or "openhands" in dr.stdout:
            for svc in services:
                if svc["name"] == "vendor-runtime":
                    svc["status"] = "running"
                    svc["docker"] = True
    except Exception:
        pass
    update_meta = get_service_update_metadata()
    for svc in services:
        meta = update_meta.get(svc["name"], {})
        svc["repo_backed"] = meta.get("repo_backed", False)
        svc["update_supported"] = meta.get("update_supported", False)
        svc["update_in_progress"] = meta.get("update_in_progress", False)
        svc["last_update"] = meta.get("last_update")
        svc["repo_source"] = {
            "repo_provider": meta.get("repo_provider"),
            "owner": meta.get("owner"),
            "repo": meta.get("repo"),
            "repo_url": meta.get("repo_url"),
            "branch": meta.get("branch"),
            "path": meta.get("path"),
        } if meta else None
    return {"services": services}


@router.get("/api/repo-sources")
def repo_sources() -> dict[str, object]:
    return {"services": list_repo_sources()}


@router.get("/api/repo-sources/{service_name}")
def repo_source(service_name: str) -> dict[str, object]:
    source = get_repo_source(service_name)
    if source is None:
        raise HTTPException(404, {"ok": False, "error": {"code": "UNKNOWN_SERVICE", "message": f"No repo source is configured for {service_name}."}})
    return {"service": source}


@router.put("/api/repo-sources/{service_name}")
def repo_source_update(service_name: str, body: RepoSourcePatch) -> dict[str, object]:
    source = update_repo_source(service_name, body.patch())
    return {"ok": True, "service": source}


@router.post("/api/repo-sources/{service_name}/reset")
def repo_source_reset(service_name: str) -> dict[str, object]:
    try:
        source = reset_repo_source(service_name)
    except KeyError:
        raise HTTPException(404, {"ok": False, "error": {"code": "UNKNOWN_SERVICE", "message": f"No default repo source exists for {service_name}."}})
    return {"ok": True, "service": source}


@router.post("/api/v2/services/{service_name}/update-latest")
async def update_service_latest(service_name: str, body: UpdateLatestBody = UpdateLatestBody()):
    if service_name not in SERVICE_CONFIGS:
        raise HTTPException(404, {"ok": False, "service": service_name, "error": {"code": "UNKNOWN_SERVICE", "message": f"Service '{service_name}' is not configured for updates."}})

    if is_self_update(service_name):
        schedule_deferred_update(service_name, restart=body.restart)
        return {
            "ok": True,
            "service": service_name,
            "deferred": True,
            "message": f"{service_name} update started in background. The server will reload automatically.",
        }

    result = await update_service(service_name, restart=body.restart)
    if not result.ok:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "service": result.service, "error": result.error},
        )
    return {
        "ok": True,
        "service": result.service,
        "branch": result.branch,
        "commit_before": result.commit_before,
        "commit_after": result.commit_after,
        "updated": result.updated,
        "restart_attempted": result.restart_attempted,
        "restart_succeeded": result.restart_succeeded,
        "message": result.message,
    }


@router.post("/api/services/{name}/start")
def start_service(name: str):
    try:
        return start_service_process(name)
    except Exception as e:
        return {"error": str(e), "started": False}


@router.post("/api/services/{name}/stop")
def stop_service(name: str):
    try:
        return stop_service_process(name)
    except Exception as e:
        return {"error": str(e), "stopped": False}


@router.post("/api/services/{name}/restart")
def restart_service(name: str):
    services = service_commands()
    if name not in services:
        return {"error": f"Unknown service: {name}", "restarted": False}
    if name == "control-plane":
        command = (
            "sleep 1; "
            "fuser -k 9877/tcp; "
            "sleep 1; "
            "cd /opt/workstation/repos/ai-agent-workstation/control-plane && "
            "nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload "
            "> /opt/workstation/logs/control-plane.log 2>&1 &"
        )
        sp.Popen(["/bin/sh", "-c", command], stdout=sp.DEVNULL, stderr=sp.DEVNULL, start_new_session=True)
        return {"message": "Restarting control-plane", "restarted": True}
    stop_result = stop_service_process(name)
    if not stop_result.get("stopped"):
        return {"error": stop_result.get("error", f"Unable to stop {name}"), "restarted": False}
    start_result = start_service_process(name)
    return {
        "message": f"Restarted {name}" if start_result.get("started") else start_result.get("message", f"Restart requested for {name}"),
        "restarted": bool(start_result.get("started")),
        "details": {"stop": stop_result, "start": start_result},
    }
