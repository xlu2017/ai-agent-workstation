"""Health-check route."""

import subprocess
import urllib.request

from fastapi import APIRouter

from api.config import AGENT_CORE_URL, BRIDGE_URL, LITELLM_URL, VENDOR_RUNTIME_URL

router = APIRouter(tags=["health"])


@router.get("/api/health")
def get_health():
    import json
    checks = {}

    for name, url in [
        ("agent_core", f"{AGENT_CORE_URL}/actions"),
        ("litellm", f"{LITELLM_URL}/health/liveliness"),
        ("vendor_runtime", f"{VENDOR_RUNTIME_URL}/api/options/config"),
        ("bridge", f"{BRIDGE_URL}/sessions"),
    ]:
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
        docker = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True,
        )
        containers = []
        for line in docker.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("\t")
                containers.append({
                    "name": parts[0],
                    "status": parts[1] if len(parts) > 1 else "?",
                    "ports": parts[2] if len(parts) > 2 else "",
                })
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
