"""Shared service management helpers (start/stop/restart, port checks)."""

import subprocess as sp
import time

from api.services.remote_desktop import check_tcp


def service_commands() -> dict:
    return {
        "agent-core": {
            "port": 3210,
            "start": "cd /opt/workstation/repos/agent-core && nohup node dist/index.js > /opt/workstation/logs/agent-core.log 2>&1 &",
        },
        "litellm": {
            "port": 4000,
            "start": "nohup /home/agent/.local/bin/litellm --config /opt/workstation/litellm-config.yaml --port 4000 > /opt/workstation/logs/litellm.log 2>&1 &",
        },
        "control-plane": {
            "port": 9877,
            "start": "cd /opt/workstation/repos/ai-agent-workstation/control-plane && nohup /home/agent/.local/bin/uvicorn api.server:app --host 0.0.0.0 --port 9877 --reload > /opt/workstation/logs/control-plane.log 2>&1 &",
        },
        "vendor-runtime": {
            "port": 3000,
            "start": "docker run -d --name vendor-runtime --network host -v /opt/workstation/repos:/opt/workspace -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/all-hands-ai/openhands:latest",
            "docker": True,
        },
        "dashboard": {
            "port": 5173,
            "start": "cd /opt/workstation/repos/ai-agent-workstation/control-plane/web && nohup pnpm dev --host 0.0.0.0 --port 5173 > /opt/workstation/logs/dashboard.log 2>&1 &",
        },
    }


def port_listening(port: int) -> bool:
    return check_tcp("127.0.0.1", port, timeout=0.5)["status"] == "reachable"


def wait_for_port(port: int, desired: bool, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_listening(port) is desired:
            return True
        time.sleep(0.25)
    return port_listening(port) is desired


def start_service_process(name: str) -> dict:
    services = service_commands()
    if name not in services:
        return {"error": f"Unknown service: {name}", "started": False}
    service = services[name]
    port = service["port"]
    if port_listening(port):
        return {"message": f"{name} already running", "started": True}
    sp.run(service["start"], shell=True, timeout=10)
    started = wait_for_port(port, True, timeout=15)
    return {"message": f"Started {name}" if started else f"Start requested for {name}", "started": started}


def stop_service_process(name: str) -> dict:
    services = service_commands()
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
    stopped = wait_for_port(port, False, timeout=10)
    return {"message": f"Stopped {name} (port {port})" if stopped else f"Stop requested for {name}", "stopped": stopped}
