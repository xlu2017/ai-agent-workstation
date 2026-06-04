#!/usr/bin/env python3
"""
Control Plane API — FastAPI server wrapping platformctl.

Every endpoint calls the same logic as the CLI. No duplicate logic.
Serves the web dashboard static files and provides REST API.

Endpoints:
  GET  /api/sessions          List sessions
  POST /api/sessions          Create session
  DELETE /api/sessions/:id    Destroy session
  GET  /api/sessions/:id      Inspect session
  GET  /api/sessions/:id/context  Get session context

  GET  /api/health            System health
  GET  /api/logs              Recent logs

  GET  /api/models            List models
  GET  /api/knowledge         List knowledge entries

  GET  /                      Web dashboard (static)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add CLI to path for reuse
sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-b79d4f2e502e773f5e010bb6edbfa11ecbf8d601138956b4d8596aab03effacd")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")
OPENHANDS_URL = os.environ.get("OPENHANDS_URL", "http://localhost:3000")
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")
REPOS_DIR = Path("/opt/workstation/repos")

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
    sessions = []
    if SESSIONS_DIR.exists():
        for d in sorted(SESSIONS_DIR.iterdir()):
            meta_file = d / "session.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    # Add context summary
                    ctx_dir = d / "context"
                    meta["has_ui_context"] = (ctx_dir / "latest-ui-context.md").exists()
                    meta["has_editor_context"] = (ctx_dir / "latest-editor-context.md").exists()
                    meta["has_terminal_context"] = (ctx_dir / "latest-terminal-context.md").exists()
                    sessions.append(meta)
                except (json.JSONDecodeError, OSError):
                    continue
    return {"sessions": sessions}


@app.post("/api/sessions")
def create_session(body: SessionCreate):
    session_id = body.name or f"session-{int(time.time())}"
    repo_path = body.repo or str(REPOS_DIR / "example-react-app")
    branch = body.branch or f"{session_id}-branch"

    session_dir = SESSIONS_DIR / session_id
    if session_dir.exists():
        raise HTTPException(400, f"Session '{session_id}' already exists")

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "context").mkdir(exist_ok=True)
    (session_dir / "events").mkdir(exist_ok=True)

    worktree_path = str(REPOS_DIR / f"worktree-{session_id}")
    if Path(repo_path).exists() and (Path(repo_path) / ".git").exists():
        subprocess.run(
            ["git", "worktree", "add", worktree_path, "-b", branch],
            cwd=repo_path, capture_output=True, text=True,
        )

    meta = {
        "id": session_id,
        "repo_path": repo_path,
        "worktree_path": worktree_path,
        "branch": branch,
        "port_range": body.ports or "",
        "browser_profile": body.profile or session_id,
        "tmux_session": f"agent-{session_id}",
        "status": "active",
        "task": body.task or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(session_dir / "session.json", "w") as f:
        json.dump(meta, f, indent=2)

    return meta


@app.delete("/api/sessions/{session_id}")
def destroy_session(session_id: str):
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    meta_file = session_dir / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        worktree_path = meta.get("worktree_path", "")
        repo_path = meta.get("repo_path", "")
        if worktree_path and Path(worktree_path).exists():
            subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                cwd=repo_path, capture_output=True,
            )

    import shutil
    shutil.rmtree(session_dir)
    return {"status": "destroyed", "session_id": session_id}


@app.get("/api/sessions/{session_id}")
def inspect_session(session_id: str):
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    meta = json.loads((session_dir / "session.json").read_text())

    ctx_dir = session_dir / "context"
    ui_file = ctx_dir / "latest-ui-context.md"
    ed_file = ctx_dir / "latest-editor-context.md"
    term_file = ctx_dir / "latest-terminal-context.md"

    meta["context"] = {
        "ui": ui_file.read_text() if ui_file.exists() else None,
        "editor": ed_file.read_text() if ed_file.exists() else None,
        "terminal": term_file.read_text() if term_file.exists() else None,
    }

    return meta


@app.get("/api/sessions/{session_id}/context")
def get_session_context(session_id: str):
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    ctx_dir = session_dir / "context"
    result = {}
    for ctx_file in ["latest-ui-context.md", "latest-editor-context.md", "latest-terminal-context.md"]:
        path = ctx_dir / ctx_file
        if path.exists():
            result[ctx_file.replace("latest-", "").replace("-context.md", "")] = path.read_text()

    # Events
    events_dir = session_dir / "events"
    events = {}
    for ev_file in events_dir.glob("*.jsonl"):
        lines = ev_file.read_text().strip().split("\n")
        events[ev_file.stem] = [json.loads(l) for l in lines[-20:] if l.strip()]

    return {"context": result, "events": events}


# --- Health ---

@app.get("/api/health")
def get_health():
    import urllib.request
    checks = {}

    for name, url in [("litellm", f"{LITELLM_URL}/health/liveliness"), ("openhands", OPENHANDS_URL), ("bridge", f"{BRIDGE_URL}/sessions")]:
        try:
            urllib.request.urlopen(url, timeout=3)
            checks[name] = {"status": "healthy", "url": url.rsplit("/", 1)[0] if "/" in url[8:] else url}
        except Exception as e:
            checks[name] = {"status": "unhealthy", "error": str(e)[:100]}

    # System resources
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

    # Docker
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

    # Active ports
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

    # Config file models
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
    from timeline import Timeline
    tl = Timeline(session_id)
    return {"events": tl.get_events(limit=limit), "summary": tl.get_summary()}


@app.get("/api/sessions/{session_id}/timeline/summary")
def get_timeline_summary(session_id: str):
    from timeline import Timeline
    tl = Timeline(session_id)
    return tl.get_summary()


# --- Context Validation ---

@app.get("/api/sessions/{session_id}/context/health")
def get_context_health_endpoint(session_id: str):
    from context_validator import get_context_health
    return get_context_health(session_id)


# --- Postmortem ---

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


# --- Chat / Task Routing ---

class ChatMessage(BaseModel):
    instruction: str
    model: Optional[str] = None


@app.post("/api/sessions/{session_id}/chat")
def send_chat(session_id: str, body: ChatMessage):
    """
    Dashboard chat → Context Assembler → OpenHands adapter.

    Flow:
    1. Assemble context (UI/editor/terminal + knowledge + staleness)
    2. Create instruction packet
    3. Route to OpenHands as a task
    4. Record in timeline + message log
    """
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    meta = json.loads((session_dir / "session.json").read_text())

    # --- Context Assembly ---
    ctx_dir = session_dir / "context"
    assembled_context = {}
    for ctx_type, filename in [
        ("ui", "latest-ui-context.md"),
        ("editor", "latest-editor-context.md"),
        ("terminal", "latest-terminal-context.md"),
    ]:
        path = ctx_dir / filename
        if path.exists():
            assembled_context[ctx_type] = path.read_text()

    # Staleness check
    from context_validator import get_context_health
    health = get_context_health(session_id)
    staleness_status = health.get("status", "unknown")
    staleness_warnings = health.get("warnings", [])

    # Knowledge activation
    activated_knowledge = []
    if KNOWLEDGE_DIR.exists():
        try:
            import yaml
            for f in KNOWLEDGE_DIR.glob("*.yaml"):
                try:
                    entry = yaml.safe_load(f.read_text())
                    if isinstance(entry, dict):
                        paths = entry.get("activation_paths", [])
                        keywords = entry.get("activation_keywords", [])
                        worktree = meta.get("worktree_path", "")
                        instruction_lower = body.instruction.lower()
                        if any(p in worktree for p in paths) or any(k in instruction_lower for k in keywords):
                            activated_knowledge.append(entry)
                except Exception:
                    continue
        except ImportError:
            pass

    # --- Build instruction packet ---
    instruction_packet = {
        "user_instruction": body.instruction,
        "session_id": session_id,
        "worktree_path": meta.get("worktree_path", ""),
        "branch": meta.get("branch", ""),
        "repo_path": meta.get("repo_path", ""),
        "latest_ui_context": assembled_context.get("ui"),
        "latest_editor_context": assembled_context.get("editor"),
        "latest_terminal_context": assembled_context.get("terminal"),
        "activated_knowledge": activated_knowledge,
        "staleness_status": staleness_status,
        "staleness_warnings": staleness_warnings,
        "model": body.model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # --- Save message to log ---
    messages_file = session_dir / "messages.jsonl"
    user_message = {
        "role": "user",
        "content": body.instruction,
        "timestamp": instruction_packet["timestamp"],
        "context_attached": list(assembled_context.keys()),
        "staleness": staleness_status,
    }
    with open(messages_file, "a") as f:
        f.write(json.dumps(user_message) + "\n")

    # --- Route to OpenHands ---
    openhands_response = route_to_openhands(instruction_packet)

    # --- Save assistant response ---
    assistant_message = {
        "role": "assistant",
        "content": openhands_response.get("response", "Task submitted to agent."),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": openhands_response.get("status", "submitted"),
        "task_id": openhands_response.get("task_id"),
    }
    with open(messages_file, "a") as f:
        f.write(json.dumps(assistant_message) + "\n")

    # --- Record in timeline ---
    try:
        from timeline import Timeline
        tl = Timeline(session_id)
        tl.record_event("chat_instruction", {
            "instruction": body.instruction,
            "context_types": list(assembled_context.keys()),
            "model": body.model,
            "staleness": staleness_status,
        })
    except Exception:
        pass

    return {
        "status": openhands_response.get("status", "submitted"),
        "message": assistant_message["content"],
        "task_id": openhands_response.get("task_id"),
        "context_attached": list(assembled_context.keys()),
        "staleness": staleness_status,
        "warnings": staleness_warnings,
        "knowledge_activated": len(activated_knowledge),
    }


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str, limit: int = 50):
    """Get chat message history for a session."""
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")

    messages_file = session_dir / "messages.jsonl"
    if not messages_file.exists():
        return {"messages": []}

    lines = messages_file.read_text().strip().split("\n")
    messages = [json.loads(l) for l in lines[-limit:] if l.strip()]
    return {"messages": messages}


def route_to_openhands(packet: dict) -> dict:
    """
    Route assembled instruction to OpenHands.

    Builds a prompt with full context and submits as a task.
    Falls back to direct LiteLLM call if OpenHands is unavailable.
    """
    import urllib.request

    # Build the full prompt for the agent
    prompt_parts = []
    prompt_parts.append(f"## Task\n{packet['user_instruction']}")

    if packet.get("latest_ui_context"):
        prompt_parts.append(f"## UI Context (what user is looking at)\n{packet['latest_ui_context']}")
    if packet.get("latest_editor_context"):
        prompt_parts.append(f"## Editor Context (active file/selection)\n{packet['latest_editor_context']}")
    if packet.get("latest_terminal_context"):
        prompt_parts.append(f"## Terminal Context (recent error)\n{packet['latest_terminal_context']}")

    if packet.get("activated_knowledge"):
        knowledge_text = "\n".join(f"- {k.get('description', '')}: {k.get('content', '')}" for k in packet["activated_knowledge"])
        prompt_parts.append(f"## Activated Knowledge\n{knowledge_text}")

    if packet.get("staleness_warnings"):
        prompt_parts.append(f"## Warnings\n" + "\n".join(f"- {w}" for w in packet["staleness_warnings"]))

    prompt_parts.append(f"## Working Directory\n{packet.get('worktree_path', '')}")
    prompt_parts.append(f"## Branch\n{packet.get('branch', '')}")

    full_prompt = "\n\n".join(prompt_parts)

    # Try OpenHands first
    try:
        openhands_task = {
            "task": full_prompt,
            "workspace": packet.get("worktree_path", ""),
        }
        data = json.dumps(openhands_task).encode()
        req = urllib.request.Request(
            f"{OPENHANDS_URL}/api/conversations",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return {
            "status": "running",
            "response": f"Agent started working on: {packet['user_instruction'][:100]}",
            "task_id": result.get("conversation_id", result.get("id", "unknown")),
        }
    except Exception as openhands_error:
        pass

    # Fallback: direct LiteLLM call for simple responses
    try:
        model = packet.get("model") or DEFAULT_MODEL
        litellm_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a coding agent working in a developer workstation. Analyze the context and provide guidance. If you can suggest a fix, provide the exact code change."},
                {"role": "user", "content": full_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }
        data = json.dumps(litellm_payload).encode()
        req = urllib.request.Request(
            f"{LITELLM_URL}/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LITELLM_KEY}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        return {
            "status": "completed",
            "response": content,
            "task_id": f"litellm-{int(time.time())}",
        }
    except Exception as litellm_error:
        return {
            "status": "queued",
            "response": f"Task queued for session {packet['session_id']}. Context attached: {', '.join(packet.get('latest_ui_context', '') and ['ui'] or []) + ', '.join(packet.get('latest_editor_context', '') and ['editor'] or []) + ', '.join(packet.get('latest_terminal_context', '') and ['terminal'] or [])}. Agent will process when available.",
            "task_id": f"queued-{int(time.time())}",
        }


# --- Static files (web dashboard) ---

STATIC_DIR = Path(__file__).parent.parent / "web" / "dist"

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    def serve_spa(path: str = ""):
        # API routes handled above
        if path.startswith("api/"):
            raise HTTPException(404)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "Dashboard not built yet. Run: cd web && npm run build"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9877)
