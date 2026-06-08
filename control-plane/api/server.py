import asyncio
#!/usr/bin/env python3
"""
Control Plane API — FastAPI server wrapping shared control-plane services.

Session lifecycle logic lives in sessions.session_manager so the API and CLI do
not duplicate worktree/session filesystem behavior.
"""

import json
import os
import base64
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Add control-plane root and CLI to path for imports
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(CONTROL_PLANE_ROOT / "cli"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from api.service_updater import (
    SERVICE_CONFIGS,
    get_service_update_metadata,
    update_service,
)

from sessions.session_manager import (
    SessionAlreadyExists,
    SessionCreateRequest,
    SessionNotFound,
    create_session as create_session_record,
    destroy_session as destroy_session_record,
    get_session_context as get_session_context_record,
    inspect_session as inspect_session_record,
    list_sessions as list_session_records,
)

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
AGENT_CORE_URL = os.environ.get("AGENT_CORE_URL", "http://localhost:3210")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "fdfe750a587cddaedd90f39afb861f67377b155b7fdbe5d39d53437b29a700ed")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")


def _get_openhands_url():
    port_file = Path("/opt/workstation/logs/openhands-port")
    if port_file.exists():
        try:
            port = int(port_file.read_text().strip())
            return f"http://localhost:{port}"
        except (ValueError, OSError):
            pass
    return "http://localhost:3010"


OPENHANDS_URL = os.environ.get("OPENHANDS_URL") or _get_openhands_url()
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")

TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
REMOTE_DESKTOP_ENV_FILE = Path(
    os.environ.get(
        "REMOTE_DESKTOP_ENV_FILE",
        "/opt/workstation/repos/jubilant-goggles/ops/remote-desktop/.env",
    )
)

app = FastAPI(title="Workstation Control Plane", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_ENV_VALUES


def _remote_desktop_file_env() -> dict[str, str]:
    if not REMOTE_DESKTOP_ENV_FILE.exists():
        return {}
    values = {}
    try:
        lines = REMOTE_DESKTOP_ENV_FILE.read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _remote_desktop_env(name: str, default: str = "") -> str:
    return os.environ.get(name) or _remote_desktop_file_env().get(name, default)


def _remote_desktop_bool(name: str, default: bool = False) -> bool:
    value = _remote_desktop_env(name)
    if value == "":
        return default
    return value.strip().lower() in TRUE_ENV_VALUES


def _remote_desktop_config():
    return {
        "enabled": _remote_desktop_bool("REMOTE_DESKTOP_ENABLED", False),
        "provider": "guacamole",
        "url": _remote_desktop_env("GUACAMOLE_URL", "/guacamole/"),
        "rdp_host": _remote_desktop_env("RDP_HOST", "dev-server"),
        "security": "tailscale_only",
        "auto_login": _remote_desktop_bool("GUACAMOLE_AUTO_LOGIN_ENABLED", False),
    }


def _guacamole_client_identifier(connection_id: str, data_source: str) -> str:
    raw_identifier = f"{connection_id}\0c\0{data_source}".encode()
    return base64.b64encode(raw_identifier).decode().rstrip("=")


def _request_guacamole_token(username: str, password: str):
    guacamole_host = _remote_desktop_env("GUACAMOLE_HOST", "127.0.0.1")
    guacamole_port = int(_remote_desktop_env("GUACAMOLE_PORT", "8080"))
    token_url = f"http://{guacamole_host}:{guacamole_port}/guacamole/api/tokens"
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5.0) as response:
        return json.loads(response.read().decode())


def _check_tcp(host: str, port: int, timeout: float = 3.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"status": "reachable"}
    except OSError as exc:
        return {"status": "unreachable", "error": str(exc)[:160]}


def _check_http(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"status": "reachable", "code": response.status}
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            return {"status": "reachable", "code": exc.code}
        return {"status": "unreachable", "code": exc.code, "error": str(exc)[:160]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": "unreachable", "error": str(exc)[:160]}


class SessionCreate(BaseModel):
    name: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    ports: Optional[str] = None
    profile: Optional[str] = None
    task: Optional[str] = None


# --- Sessions ---

@app.get("/api/sessions")
def list_sessions():
    return {"sessions": list_session_records()}


@app.post("/api/sessions")
def create_session(body: SessionCreate):
    try:
        return create_session_record(
            SessionCreateRequest(
                name=body.name,
                repo=body.repo,
                branch=body.branch,
                ports=body.ports,
                profile=body.profile,
                task=body.task,
            )
        )
    except SessionAlreadyExists as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/sessions/{session_id}")
def destroy_session(session_id: str):
    try:
        return destroy_session_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/sessions/{session_id}")
def inspect_session(session_id: str):
    try:
        return inspect_session_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/sessions/{session_id}/context")
def get_session_context(session_id: str):
    try:
        return get_session_context_record(session_id)
    except SessionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


# --- Health ---

@app.get("/api/health")
def get_health():
    import urllib.request
    checks = {}

    for name, url in [("agent_core", f"{AGENT_CORE_URL}/actions"), ("litellm", f"{LITELLM_URL}/health/liveliness"), ("openhands", f"{OPENHANDS_URL}/api/options/config"), ("bridge", f"{BRIDGE_URL}/sessions")]:
        try:
            urllib.request.urlopen(url, timeout=3)
            checks[name] = {"status": "healthy", "url": url.rsplit("/", 1)[0] if "/" in url[8:] else url}
        except Exception as e:
            checks[name] = {"status": "unhealthy", "error": str(e)[:100]}

    try:
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        parts = disk.stdout.strip().split("\n")[-1].split()
        checks["disk"] = {"used": parts[2], "available": parts[3], "percent": parts[4]}
    except Exception:
        checks["disk"] = {}

    try:
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True)
        parts = mem.stdout.strip().split("\n")[1].split()
        checks["memory"] = {"total": parts[1], "used": parts[2], "available": parts[6]}
    except Exception:
        checks["memory"] = {}

    try:
        load = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True)
        parts = load.stdout.split()
        checks["cpu"] = {"load_1m": parts[0], "load_5m": parts[1], "load_15m": parts[2]}
    except Exception:
        checks["cpu"] = {}

    try:
        docker = subprocess.run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"], capture_output=True, text=True)
        containers = []
        for line in docker.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("\t")
                containers.append({"name": parts[0], "status": parts[1] if len(parts) > 1 else "?", "ports": parts[2] if len(parts) > 2 else ""})
        checks["docker"] = containers
    except Exception:
        checks["docker"] = []

    try:
        ports_result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        active_ports = []
        for line in ports_result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 4:
                addr = parts[3]
                if ":" in addr:
                    port = addr.rsplit(":", 1)[-1]
                    if port.isdigit() and int(port) < 10000:
                        active_ports.append(int(port))
        checks["active_ports"] = sorted(set(active_ports))
    except Exception:
        checks["active_ports"] = []

    return checks


@app.get("/api/v2/remote-desktop/config")
def get_remote_desktop_config():
    return _remote_desktop_config()


@app.post("/api/v2/remote-desktop/token")
def create_remote_desktop_token():
    config = _remote_desktop_config()
    if not config["enabled"]:
        raise HTTPException(409, "Remote desktop is not enabled")
    if not config["auto_login"]:
        raise HTTPException(409, "Guacamole auto-login is not enabled")

    username = _remote_desktop_env("GUACAMOLE_USERNAME")
    password = _remote_desktop_env("GUACAMOLE_PASSWORD")
    if not username or not password:
        raise HTTPException(500, "Guacamole credentials are not configured")

    try:
        token = _request_guacamole_token(username, password)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(502, f"Unable to authenticate with Guacamole: {str(exc)[:160]}") from exc

    data_source = token.get("dataSource", _remote_desktop_env("GUACAMOLE_DATA_SOURCE", "postgresql"))
    connection_id = _remote_desktop_env("GUACAMOLE_CONNECTION_ID", "1")
    client_id = _guacamole_client_identifier(connection_id, data_source)
    guacamole_url = config["url"].rstrip("/")

    return {
        "authToken": token["authToken"],
        "username": token.get("username", username),
        "dataSource": data_source,
        "availableDataSources": token.get("availableDataSources", [data_source]),
        "connection_url": f"{guacamole_url}/#/client/{client_id}",
    }


@app.get("/api/v2/remote-desktop/health")
def get_remote_desktop_health():
    config = _remote_desktop_config()
    guacamole_host = _remote_desktop_env("GUACAMOLE_HOST", "127.0.0.1")
    guacamole_port = int(_remote_desktop_env("GUACAMOLE_PORT", "8080"))
    guacamole_url = _remote_desktop_env(
        "GUACAMOLE_HEALTH_URL",
        f"http://{guacamole_host}:{guacamole_port}/guacamole/",
    )
    rdp_host = _remote_desktop_env("RDP_HOST", "dev-server")
    rdp_port = int(_remote_desktop_env("RDP_PORT", "3389"))
    guacd_host = _remote_desktop_env("GUACD_HOST")
    guacd_port = int(_remote_desktop_env("GUACD_PORT", "4822"))

    guacamole = _check_http(guacamole_url)
    rdp = _check_tcp(rdp_host, rdp_port)
    guacd = _check_tcp(guacd_host, guacd_port) if guacd_host else {"status": "not_configured"}

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


# --- Logs ---

@app.get("/api/logs")
def get_logs(service: str = None, lines: int = 50):
    result = {}

    if service in (None, "litellm"):
        try:
            r = subprocess.run(["docker", "logs", "--tail", str(lines), "litellm"], capture_output=True, text=True)
            result["litellm"] = (r.stdout + r.stderr)[-5000:]
        except Exception:
            result["litellm"] = ""

    if service in (None, "bridge"):
        events_log = Path("/opt/workstation/glue/ui-bridge/events.jsonl")
        if events_log.exists():
            log_lines = events_log.read_text().strip().split("\n")
            result["bridge"] = log_lines[-lines:]
        else:
            result["bridge"] = []

    return result


# --- Models ---

@app.get("/api/models")
def list_models():
    import urllib.request
    models = []

    try:
        req = urllib.request.urlopen(f"{LITELLM_URL}/models", timeout=5)
        data = json.loads(req.read())
        models = data.get("data", [])
    except Exception:
        pass

    config_path = Path("/opt/workstation/config/litellm_config.yaml")
    config_models = []
    if config_path.exists():
        try:
            import yaml
            config = yaml.safe_load(config_path.read_text())
            config_models = config.get("model_list", [])
        except Exception:
            pass

    return {"live": models, "configured": config_models}


# --- Knowledge ---

@app.get("/api/knowledge")
def list_knowledge():
    entries = []
    if KNOWLEDGE_DIR.exists():
        try:
            import yaml
            for f in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
                try:
                    entry = yaml.safe_load(f.read_text())
                    if isinstance(entry, dict):
                        entries.append(entry)
                except Exception:
                    continue
        except ImportError:
            pass
    return {"entries": entries}


# --- Timeline ---

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))


@app.get("/api/sessions/{session_id}/timeline")
def get_timeline(session_id: str, limit: int = 100):
    """Get session timeline with tool call details from events.jsonl."""
    session_dir = SESSIONS_DIR / session_id
    events_file = session_dir / "events" / "events.jsonl"

    events = []
    if events_file.exists():
        for line in events_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    summary = {
        "total_events": len(events),
        "tool_calls": sum(1 for e in events if e.get("type") == "tool_call"),
        "files_edited": len(set(
            e.get("args", {}).get("path", "")
            for e in events
            if e.get("type") == "tool_call" and e.get("tool") in ("write_file", "apply_patch") and e.get("success")
        )),
        "commands_run": sum(1 for e in events if e.get("type") == "tool_call" and e.get("tool") == "run_command"),
        "commits": sum(1 for e in events if e.get("type") == "tool_call" and e.get("tool") == "git_commit" and e.get("success")),
        "tasks_completed": sum(1 for e in events if e.get("type") == "task_complete"),
        "cost_usd": 0.0,
    }

    try:
        from timeline import Timeline
        tl = Timeline(session_id)
        old_summary = tl.get_summary()
        if old_summary.get("cost_usd"):
            summary["cost_usd"] = old_summary["cost_usd"]
    except Exception:
        pass

    return {"events": events[-limit:], "summary": summary}


@app.get("/api/sessions/{session_id}/timeline/summary")
def get_timeline_summary(session_id: str):
    from timeline import Timeline
    tl = Timeline(session_id)
    return tl.get_summary()


@app.get("/api/sessions/{session_id}/context/health")
def get_context_health_endpoint(session_id: str):
    from context_validator import get_context_health
    return get_context_health(session_id)


@app.post("/api/sessions/{session_id}/postmortem")
def generate_postmortem(session_id: str, reason: str = ""):
    from postmortem import Postmortem
    pm = Postmortem(session_id)
    return pm.generate(reason)


@app.get("/api/knowledge/proposed")
def list_proposed_triggers():
    proposed_dir = KNOWLEDGE_DIR / "proposed"
    if not proposed_dir.exists():
        return {"triggers": []}
    triggers = []
    for f in proposed_dir.glob("*"):
        try:
            import yaml
            triggers.append(yaml.safe_load(f.read_text()))
        except Exception:
            try:
                triggers.append(json.loads(f.read_text()))
            except Exception:
                continue
    return {"triggers": triggers}


@app.post("/api/knowledge/approve/{trigger_id}")
def approve_knowledge_trigger(trigger_id: str):
    from postmortem import approve_trigger
    if approve_trigger(trigger_id):
        return {"status": "approved", "trigger_id": trigger_id}
    raise HTTPException(404, f"Trigger '{trigger_id}' not found")


class ChatMessage(BaseModel):
    instruction: str
    model: Optional[str] = None
    executor: Optional[str] = None
    execution_mode: Optional[str] = "finite"  # finite | open_ended | loop


# --- Chat/Task endpoint (end-to-end prompt flow) ---

# Background task tracking
_running_tasks: dict[str, asyncio.Task] = {}

@app.post("/api/sessions/{session_id}/chat")
async def session_chat(session_id: str, body: ChatMessage):
    """Submit a prompt for execution in a session.

    Flow: route → policy check → advisory plan → execute via OpenHands → events.
    Runs execution in background so event polling works during execution.
    """
    from execution.prompt_handler import handle_prompt, TaskState
    import uuid as _uuid

    task_id = f"task-{_uuid.uuid4().hex[:12]}"

    # Reject concurrent requests for the same session
    existing = _running_tasks.get(session_id)
    if existing and not existing.done():
        return JSONResponse(
            status_code=409,
            content={"error": "A task is already running for this session", "session_id": session_id},
        )

    async def _run_in_background():
        try:
            result = await handle_prompt(
                session_id=session_id,
                instruction=body.instruction,
                model=body.model or DEFAULT_MODEL,
                execution_mode=body.execution_mode or "finite",
            )
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    bg_task = asyncio.create_task(_run_in_background())
    _running_tasks[session_id] = bg_task

    # Wait briefly to capture initial events (routing, planning)
    await asyncio.sleep(0.5)

    # If task completed quickly, return full result
    if bg_task.done():
        result = bg_task.result()
        if result:
            return {
                "task_id": result.task_id,
                "session_id": result.session_id,
                "state": result.state.value,
                "message": result.message,
                "routing_decision": getattr(result, "routing_decision", ""),
                "plan_summary": str(getattr(result, "plan_summary", ""))[:200],
                "error": getattr(result, "error", ""),
                "events_path": str(getattr(result, "events_path", "")),
                "metadata": getattr(result, "metadata", {}),
            }
        return {"task_id": task_id, "session_id": session_id, "state": "failed", "message": "Execution error"}

    # Task still running — return immediately so event polling can work
    return {
        "task_id": task_id,
        "session_id": session_id,
        "state": "working",
        "message": "Execution started. Poll events for progress.",
    }




@app.get("/api/sessions/{session_id}/chat/status")
async def session_chat_status(session_id: str):
    """Check if background chat execution is complete."""
    from execution.prompt_handler import TaskState
    bg_task = _running_tasks.get(session_id)
    if not bg_task:
        return {"state": "unknown", "message": "No active task"}
    if not bg_task.done():
        return {"state": "working", "message": "Still executing..."}
    result = bg_task.result()
    _running_tasks.pop(session_id, None)
    if not result:
        return {"state": "failed", "message": "Execution error"}
    return {
        "task_id": result.task_id,
        "session_id": result.session_id,
        "state": result.state.value,
        "message": result.message,
        "routing_decision": getattr(result, "routing_decision", ""),
        "plan_summary": str(getattr(result, "plan_summary", ""))[:200],
        "error": getattr(result, "error", ""),
    }

@app.get("/api/sessions/{session_id}/events/stream")
async def stream_session_events(session_id: str, after: int = 0):
    """Stream events for a session via SSE. Returns new events since 'after' sequence number."""
    import json as _json
    events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    events = []
    if events_file.exists():
        all_lines = events_file.read_text().strip().split("\n")
        for idx, line in enumerate(all_lines):
            if line.strip():
                try:
                    ev = _json.loads(line)
                    # Use index as fallback sequence number
                    seq = ev.get("sequence", idx + 1)
                    if seq > after:
                        ev["_seq"] = seq
                        events.append(ev)
                except Exception:
                    continue
    total = len(events) + after
    return {"events": events, "total": total}


@app.get("/api/sessions/{session_id}/events/stream")
async def stream_session_events(session_id: str, after: int = 0):
    """Stream events for a session via SSE. Returns new events since 'after' sequence number."""
    import json as _json
    events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    events = []
    if events_file.exists():
        all_lines = events_file.read_text().strip().split("\n")
        for idx, line in enumerate(all_lines):
            if line.strip():
                try:
                    ev = _json.loads(line)
                    # Use index as fallback sequence number
                    seq = ev.get("sequence", idx + 1)
                    if seq > after:
                        ev["_seq"] = seq
                        events.append(ev)
                except Exception:
                    continue
    total = len(events) + after
    return {"events": events, "total": total}


@app.get("/api/sessions/{session_id}/state")
def get_session_state(session_id: str):
    """Get truthful execution state for a session."""
    from execution.prompt_handler import get_task_state
    return get_task_state(session_id)


@app.get("/api/sessions/{session_id}/events")
def get_session_events(session_id: str, limit: int = 100):
    """Get raw events from session's events.jsonl."""
    events_path = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    if not events_path.exists():
        return {"events": [], "total": 0}
    events = []
    for line in events_path.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"events": events[-limit:], "total": len(events)}


@app.get("/api/browse")
def browse_directory(path: str = "/opt/workstation/repos"):
    """Browse filesystem directories for repo selection."""
    from pathlib import Path as P
    target = P(path).resolve()
    # Security: only allow browsing under safe roots
    safe_roots = [P("/opt/workstation"), P("/home/agent"), P("/tmp")]
    if not any(str(target).startswith(str(r)) for r in safe_roots):
        return {"error": "Access denied", "path": str(target), "entries": []}
    if not target.exists():
        return {"error": "Path not found", "path": str(target), "entries": []}
    if not target.is_dir():
        return {"error": "Not a directory", "path": str(target), "entries": []}
    entries = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith('.') and item.name != '.git':
                continue
            if item.is_dir():
                is_repo = (item / ".git").exists()
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": True,
                    "is_repo": is_repo,
                })
    except PermissionError:
        return {"error": "Permission denied", "path": str(target), "entries": []}
    return {"path": str(target), "entries": entries, "parent": str(target.parent)}


@app.get("/api/services")
def list_services():
    """List known services with port, status, and PID."""
    import subprocess as sp
    services = [
        {"name": "agent-core", "port": 3210, "description": "Advisory memory/planning", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "litellm", "port": 4000, "description": "LLM proxy gateway", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "control-plane", "port": 9877, "description": "FastAPI orchestrator", "can_start": True, "can_stop": False, "can_restart": True},
        {"name": "openhands", "port": 3000, "description": "Execution runtime (Docker)", "can_start": True, "can_stop": True, "can_restart": True},
        {"name": "dashboard", "port": 5173, "description": "Web UI (Vite dev)", "can_start": True, "can_stop": True, "can_restart": True},
    ]
    # Check which ports are actually listening
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
    # Also check docker for openhands
    try:
        dr = sp.run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                    capture_output=True, text=True, timeout=5)
        if "openhands" in dr.stdout:
            for svc in services:
                if svc["name"] == "openhands":
                    svc["status"] = "running"
                    svc["docker"] = True
    except Exception:
        pass
    # Enrich with update metadata for repo-backed services
    update_meta = get_service_update_metadata()
    for svc in services:
        meta = update_meta.get(svc["name"], {})
        svc["repo_backed"] = meta.get("repo_backed", False)
        svc["update_supported"] = meta.get("update_supported", False)
        svc["update_in_progress"] = meta.get("update_in_progress", False)
        svc["last_update"] = meta.get("last_update")
    return {"services": services}


class UpdateLatestBody(BaseModel):
    restart: bool = True


@app.post("/api/v2/services/{service_name}/update-latest")
async def update_service_latest(service_name: str, body: UpdateLatestBody = UpdateLatestBody()):
    """Fetch the latest code from GitHub for a repo-backed service."""
    if service_name not in SERVICE_CONFIGS:
        raise HTTPException(404, {"ok": False, "service": service_name, "error": {"code": "UNKNOWN_SERVICE", "message": f"Service '{service_name}' is not configured for updates."}})
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


def _service_commands():
    return {
        "agent-core": {
            "port": 3210,
            "start": "cd /opt/workstation/repos/agent-core && nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
        },
        "litellm": {
            "port": 4000,
            "start": "nohup litellm --config /opt/workstation/litellm-config.yaml --port 4000 > /opt/workstation/logs/litellm.log 2>&1 &",
        },
        "control-plane": {
            "port": 9877,
            "start": "cd /opt/workstation/repos/jubilant-goggles/control-plane && nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload > /opt/workstation/logs/control-plane.log 2>&1 &",
        },
        "openhands": {
            "port": 3000,
            "start": "docker run -d --name openhands --network host -v /opt/workstation/repos:/opt/workspace -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/all-hands-ai/openhands:latest",
            "docker": True,
        },
        "dashboard": {
            "port": 5173,
            "start": "cd /opt/workstation/control-plane/web && nohup pnpm dev --host 0.0.0.0 --port 5173 > /opt/workstation/logs/dashboard.log 2>&1 &",
        },
    }


def _port_listening(port: int) -> bool:
    return _check_tcp("127.0.0.1", port, timeout=0.5)["status"] == "reachable"


def _wait_for_port(port: int, desired: bool, timeout: float = 10.0) -> bool:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_listening(port) is desired:
            return True
        time.sleep(0.25)
    return _port_listening(port) is desired


def _start_service_process(name: str):
    import subprocess as sp
    services = _service_commands()
    if name not in services:
        return {"error": f"Unknown service: {name}", "started": False}
    service = services[name]
    port = service["port"]
    if _port_listening(port):
        return {"message": f"{name} already running", "started": True}
    sp.run(service["start"], shell=True, timeout=10)
    started = _wait_for_port(port, True, timeout=15)
    return {"message": f"Started {name}" if started else f"Start requested for {name}", "started": started}


def _stop_service_process(name: str):
    import subprocess as sp
    services = _service_commands()
    if name not in services:
        return {"error": f"Unknown service: {name}", "stopped": False}
    if name == "control-plane":
        return {"error": "Use restart for control-plane; stop is disabled from the dashboard", "stopped": False}
    service = services[name]
    port = service["port"]
    if service.get("docker"):
        try:
            sp.run(["docker", "stop", name], timeout=15)
            sp.run(["docker", "rm", name], timeout=5)
        except Exception as exc:
            return {"error": str(exc), "stopped": False}
    else:
        sp.run(f"fuser -k {port}/tcp", shell=True, timeout=5)
    stopped = _wait_for_port(port, False, timeout=10)
    return {"message": f"Stopped {name} (port {port})" if stopped else f"Stop requested for {name}", "stopped": stopped}


@app.post("/api/services/{name}/start")
def start_service(name: str):
    """Start a known service."""
    try:
        return _start_service_process(name)
    except Exception as e:
        return {"error": str(e), "started": False}


@app.post("/api/services/{name}/stop")
def stop_service(name: str):
    """Stop a known service by killing its port or docker container."""
    try:
        return _stop_service_process(name)
    except Exception as e:
        return {"error": str(e), "stopped": False}


@app.post("/api/services/{name}/restart")
def restart_service(name: str):
    """Restart a known service from the control-plane process."""
    import subprocess as sp
    services = _service_commands()
    if name not in services:
        return {"error": f"Unknown service: {name}", "restarted": False}
    if name == "control-plane":
        command = (
            "sleep 1; "
            "fuser -k 9877/tcp; "
            "sleep 1; "
            "cd /opt/workstation/repos/jubilant-goggles/control-plane && "
            "nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload "
            "> /opt/workstation/logs/control-plane.log 2>&1 &"
        )
        sp.Popen(["/bin/sh", "-c", command], stdout=sp.DEVNULL, stderr=sp.DEVNULL, start_new_session=True)
        return {"message": "Restarting control-plane", "restarted": True}
    stop_result = _stop_service_process(name)
    if not stop_result.get("stopped"):
        return {"error": stop_result.get("error", f"Unable to stop {name}"), "restarted": False}
    start_result = _start_service_process(name)
    return {
        "message": f"Restarted {name}" if start_result.get("started") else start_result.get("message", f"Restart requested for {name}"),
        "restarted": bool(start_result.get("started")),
        "details": {"stop": stop_result, "start": start_result},
    }


@app.post("/api/open-file-manager")
def open_file_manager(path: str = "/opt/workstation/repos"):
    """Open the OS file manager at a given path."""
    import subprocess as sp
    try:
        sp.Popen(["xdg-open", path], env={**os.environ, "DISPLAY": ":10", "XAUTHORITY": "/home/agent/.Xauthority"})
        return {"message": f"Opened file manager at {path}", "opened": True}
    except Exception as e:
        return {"error": str(e), "opened": False}



@app.post("/api/pick-folder")
def pick_folder(start_path: str = "/opt/workstation/repos"):
    """Open a native folder picker dialog on the visible desktop."""
    import subprocess as sp
    try:
        result = sp.run(
            ["/opt/workstation/pick-folder.sh", start_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"path": result.stdout.strip(), "selected": True}
        return {"path": None, "selected": False, "message": "No folder selected"}
    except sp.TimeoutExpired:
        return {"path": None, "selected": False, "message": "Dialog timed out"}
    except Exception as e:
        return {"error": str(e), "selected": False}


@app.post("/api/prewarm-picker")
def prewarm_picker():
    """Pre-warm the zenity process so Browse opens faster next time."""
    import subprocess as sp
    # Just verify zenity is accessible - no actual window opened
    try:
        sp.run(["zenity", "--version"], capture_output=True, timeout=2)
        return {"ready": True}
    except Exception:
        return {"ready": False}
