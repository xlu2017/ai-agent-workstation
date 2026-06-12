"""Filesystem browsing, folder picker, and log routes."""

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["filesystem"])


@router.get("/api/browse")
def browse_directory(path: str = "/opt/workstation/repos"):
    target = Path(path).resolve()
    safe_roots = [Path("/opt/workstation"), Path("/home/agent"), Path("/tmp")]
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


@router.get("/api/logs")
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


@router.post("/api/open-file-manager")
def open_file_manager(path: str = "/opt/workstation/repos"):
    try:
        subprocess.Popen(
            ["xdg-open", path],
            env={**os.environ, "DISPLAY": ":10", "XAUTHORITY": "/home/agent/.Xauthority"},
        )
        return {"message": f"Opened file manager at {path}", "opened": True}
    except Exception as e:
        return {"error": str(e), "opened": False}


@router.post("/api/pick-folder")
def pick_folder(start_path: str = "/opt/workstation/repos"):
    try:
        result = subprocess.run(
            ["/opt/workstation/pick-folder.sh", start_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"path": result.stdout.strip(), "selected": True}
        return {"path": None, "selected": False, "message": "No folder selected"}
    except subprocess.TimeoutExpired:
        return {"path": None, "selected": False, "message": "Dialog timed out"}
    except Exception as e:
        return {"error": str(e), "selected": False}


@router.post("/api/prewarm-picker")
def prewarm_picker():
    try:
        subprocess.run(["zenity", "--version"], capture_output=True, timeout=2)
        return {"ready": True}
    except Exception:
        return {"ready": False}
