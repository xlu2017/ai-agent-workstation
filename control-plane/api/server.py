#!/usr/bin/env python3
"""
Control Plane API — FastAPI server wrapping shared control-plane services.

Session lifecycle logic lives in sessions.session_manager so the API and CLI do
not duplicate worktree/session filesystem behavior.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Add control-plane root and CLI to path for imports
CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))
sys.path.insert(0, str(CONTROL_PLANE_ROOT / "cli"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

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

app = FastAPI(title="Workstation Control Plane", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# --- Chat/Task endpoint (end-to-end prompt flow) ---

@app.post("/api/sessions/{session_id}/chat")
async def session_chat(session_id: str, body: ChatMessage):
    """Submit a prompt for execution in a session.

    Flow: route → policy check → advisory plan → execute via OpenHands → events.
    """
    from execution.prompt_handler import handle_prompt, TaskState
    try:
        result = await handle_prompt(
            session_id=session_id,
            instruction=body.instruction,
            model=body.model or DEFAULT_MODEL,
        )
        status_code = 200
        if result.state == TaskState.BLOCKED:
            status_code = 202  # Accepted but blocked
        elif result.state == TaskState.FAILED:
            status_code = 500

        return {
            "task_id": result.task_id,
            "session_id": result.session_id,
            "state": result.state.value,
            "message": result.message,
            "routing_decision": result.routing_decision,
            "plan_summary": result.plan_summary,
            "error": result.error,
            "events_path": result.events_path,
            "metadata": result.metadata,
        }
    except Exception as e:
        raise HTTPException(500, f"Prompt handling failed: {e}") from e


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
        {"name": "agent-core", "port": 3210, "description": "Advisory memory/planning"},
        {"name": "litellm", "port": 4000, "description": "LLM proxy gateway"},
        {"name": "control-plane", "port": 9877, "description": "FastAPI orchestrator"},
        {"name": "openhands", "port": 3000, "description": "Execution runtime (Docker)"},
        {"name": "dashboard", "port": 5173, "description": "Web UI (Vite dev)"},
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
    return {"services": services}


@app.post("/api/services/{name}/start")
def start_service(name: str):
    """Start a known service."""
    import subprocess as sp
    commands = {
        "agent-core": "cd /opt/workstation/repos/agent-core && nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
        "litellm": "nohup litellm --config /opt/workstation/litellm-config.yaml --port 4000 > /opt/workstation/logs/litellm.log 2>&1 &",
        "openhands": "docker run -d --name openhands --network host -v /opt/workstation/repos:/opt/workspace -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/all-hands-ai/openhands:latest",
        "dashboard": "cd /opt/workstation/control-plane/web && nohup pnpm dev --host 0.0.0.0 --port 5173 > /opt/workstation/logs/dashboard.log 2>&1 &",
    }
    if name not in commands:
        return {"error": f"Unknown service: {name}", "started": False}
    try:
        sp.run(commands[name], shell=True, timeout=10)
        return {"message": f"Started {name}", "started": True}
    except Exception as e:
        return {"error": str(e), "started": False}


@app.post("/api/services/{name}/stop")
def stop_service(name: str):
    """Stop a known service by killing its port or docker container."""
    import subprocess as sp
    ports = {"agent-core": 3210, "litellm": 4000, "openhands": 3000, "dashboard": 5173}
    if name == "openhands":
        try:
            sp.run(["docker", "stop", "openhands"], timeout=15)
            sp.run(["docker", "rm", "openhands"], timeout=5)
            return {"message": "Stopped openhands container", "stopped": True}
        except Exception as e:
            return {"error": str(e), "stopped": False}
    if name not in ports:
        return {"error": f"Unknown service: {name}", "stopped": False}
    port = ports[name]
    try:
        sp.run(f"fuser -k {port}/tcp", shell=True, timeout=5)
        return {"message": f"Stopped {name} (port {port})", "stopped": True}
    except Exception as e:
        return {"error": str(e), "stopped": False}


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
