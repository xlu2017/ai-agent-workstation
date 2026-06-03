#!/usr/bin/env python3
"""
Cross-Session Service Leasing — Port allocator, DB clones, lock manager.

Multiple agents can share services when safe or get isolated instances.
Manages port allocation, DB clones, and resource locks.

MCP Tools:
  lease_port         — Allocate a port range for a session
  release_port       — Release a port allocation
  lease_service      — Lease a shared or isolated service (DB, Redis, etc)
  release_service    — Release a service lease
  list_leases        — Show all active leases
  check_conflicts    — Check for port/service conflicts between sessions
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
LEASES_FILE = Path(os.environ.get("LEASES_FILE", "/opt/workstation/sessions/.leases.json"))

# Port ranges available for session allocation
PORT_RANGE_START = 5000
PORT_RANGE_END = 9000
PORTS_PER_SESSION = 10


def load_leases():
    """Load all active leases."""
    if LEASES_FILE.exists():
        return json.loads(LEASES_FILE.read_text())
    return {"ports": {}, "services": {}, "locks": {}}


def save_leases(leases):
    """Save leases to disk."""
    LEASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEASES_FILE, "w") as f:
        json.dump(leases, f, indent=2)


def is_port_in_use(port):
    """Check if a port is currently in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("localhost", port)) == 0
    except Exception:
        return False


def allocate_port_range(session_id, count=PORTS_PER_SESSION):
    """Allocate a contiguous port range for a session."""
    leases = load_leases()

    # Check if session already has a port allocation
    if session_id in leases["ports"]:
        return leases["ports"][session_id]

    # Find allocated ranges
    allocated = set()
    for alloc in leases["ports"].values():
        start = alloc["start"]
        end = alloc["end"]
        for p in range(start, end + 1):
            allocated.add(p)

    # Find first available contiguous range
    for start in range(PORT_RANGE_START, PORT_RANGE_END - count, count):
        candidate_range = set(range(start, start + count))
        if not candidate_range.intersection(allocated):
            # Check if any ports are actually in use
            all_free = all(not is_port_in_use(p) for p in candidate_range)
            if all_free:
                allocation = {
                    "session_id": session_id,
                    "start": start,
                    "end": start + count - 1,
                    "count": count,
                    "allocated_at": datetime.now(timezone.utc).isoformat(),
                }
                leases["ports"][session_id] = allocation
                save_leases(leases)

                # Update session metadata
                meta_file = SESSIONS_DIR / session_id / "session.json"
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text())
                    meta["port_range"] = f"{start}-{start + count - 1}"
                    with open(meta_file, "w") as f:
                        json.dump(meta, f, indent=2)

                return allocation

    return {"error": "No available port range found."}


def release_port_range(session_id):
    """Release a port allocation."""
    leases = load_leases()
    if session_id in leases["ports"]:
        released = leases["ports"].pop(session_id)
        save_leases(leases)
        return {"released": released}
    return {"error": "No port allocation found for session."}


def lease_service(session_id, service_type, mode="shared"):
    """Lease a service (database, Redis, etc)."""
    leases = load_leases()

    service_key = f"{session_id}:{service_type}"

    if service_key in leases["services"]:
        return leases["services"][service_key]

    lease = {
        "session_id": session_id,
        "service_type": service_type,
        "mode": mode,  # shared or isolated
        "leased_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }

    if mode == "isolated":
        # For isolated mode, create a dedicated instance
        if service_type == "postgres":
            port_alloc = leases["ports"].get(session_id, {})
            db_port = port_alloc.get("start", 5432) + 5  # Use offset from allocated range
            lease["connection"] = {
                "host": "localhost",
                "port": db_port,
                "database": f"session_{session_id.replace('-', '_')}",
                "user": "agent",
            }
            lease["docker_compose_project"] = f"workstation-{session_id}"
        elif service_type == "redis":
            port_alloc = leases["ports"].get(session_id, {})
            redis_port = port_alloc.get("start", 6379) + 6
            lease["connection"] = {
                "host": "localhost",
                "port": redis_port,
            }
    else:
        # Shared mode: use the default shared instance
        if service_type == "postgres":
            lease["connection"] = {
                "host": "localhost",
                "port": 5432,
                "database": "shared_dev",
                "user": "agent",
                "note": "Read-only recommended for shared mode",
            }
        elif service_type == "redis":
            lease["connection"] = {
                "host": "localhost",
                "port": 6379,
                "note": "Use key prefix: session:{session_id}:",
            }

    leases["services"][service_key] = lease
    save_leases(leases)
    return lease


def release_service(session_id, service_type):
    """Release a service lease."""
    leases = load_leases()
    service_key = f"{session_id}:{service_type}"
    if service_key in leases["services"]:
        released = leases["services"].pop(service_key)
        save_leases(leases)
        return {"released": released}
    return {"error": "No service lease found."}


def acquire_lock(session_id, resource):
    """Acquire a lock on a resource."""
    leases = load_leases()

    if resource in leases["locks"]:
        holder = leases["locks"][resource]
        if holder["session_id"] != session_id:
            return {
                "error": f"Resource '{resource}' is locked by session '{holder['session_id']}'.",
                "holder": holder,
            }

    leases["locks"][resource] = {
        "session_id": session_id,
        "resource": resource,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    save_leases(leases)
    return {"locked": True, "resource": resource}


def release_lock(session_id, resource):
    """Release a lock."""
    leases = load_leases()
    if resource in leases["locks"]:
        holder = leases["locks"][resource]
        if holder["session_id"] == session_id:
            leases["locks"].pop(resource)
            save_leases(leases)
            return {"released": True}
        return {"error": f"Lock held by different session: {holder['session_id']}"}
    return {"error": "No lock found."}


def check_conflicts(session_id=None):
    """Check for port/service conflicts."""
    leases = load_leases()
    conflicts = []

    # Check for port conflicts with running processes
    for sid, alloc in leases["ports"].items():
        for port in range(alloc["start"], alloc["end"] + 1):
            if is_port_in_use(port):
                # Check if it's being used by the expected session
                conflicts.append({
                    "type": "port_in_use",
                    "session": sid,
                    "port": port,
                })

    # Check for stale leases (sessions that no longer exist)
    for sid in list(leases["ports"].keys()):
        session_dir = SESSIONS_DIR / sid
        if not session_dir.exists():
            conflicts.append({
                "type": "stale_lease",
                "session": sid,
                "resource": "ports",
            })

    return conflicts


def list_all_leases():
    """List all active leases."""
    return load_leases()


# --- MCP Tools ---

TOOLS = [
    {
        "name": "lease_port",
        "description": "Allocate a port range for a session. Returns start/end ports.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "count": {"type": "integer", "description": "Number of ports (default 10)."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "release_port",
        "description": "Release a port allocation for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    {
        "name": "lease_service",
        "description": "Lease a service (postgres, redis) in shared or isolated mode.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "service_type": {"type": "string", "enum": ["postgres", "redis"]},
                "mode": {"type": "string", "enum": ["shared", "isolated"], "description": "shared=reuse existing, isolated=new instance"},
            },
            "required": ["session_id", "service_type"],
        },
    },
    {
        "name": "release_service",
        "description": "Release a service lease.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "service_type": {"type": "string"},
            },
            "required": ["session_id", "service_type"],
        },
    },
    {
        "name": "acquire_lock",
        "description": "Acquire a lock on a shared resource (prevents other sessions from modifying it).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "resource": {"type": "string", "description": "Resource identifier to lock."},
            },
            "required": ["session_id", "resource"],
        },
    },
    {
        "name": "release_lock",
        "description": "Release a resource lock.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "resource": {"type": "string"},
            },
            "required": ["session_id", "resource"],
        },
    },
    {
        "name": "list_leases",
        "description": "List all active port allocations, service leases, and locks.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_conflicts",
        "description": "Check for port/service conflicts between sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Optional: check for specific session."},
            },
        },
    },
]


def handle_lease_port(args):
    result = allocate_port_range(args["session_id"], args.get("count", PORTS_PER_SESSION))
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": f"Ports {result['start']}-{result['end']} allocated for session `{args['session_id']}`."}]}


def handle_release_port(args):
    result = release_port_range(args["session_id"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": "Port allocation released."}]}


def handle_lease_service(args):
    result = lease_service(args["session_id"], args["service_type"], args.get("mode", "shared"))
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    conn = result.get("connection", {})
    return {"content": [{"type": "text", "text": f"Service `{args['service_type']}` leased ({args.get('mode', 'shared')} mode).\nConnection: {json.dumps(conn, indent=2)}"}]}


def handle_release_service(args):
    result = release_service(args["session_id"], args["service_type"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": "Service lease released."}]}


def handle_acquire_lock(args):
    result = acquire_lock(args["session_id"], args["resource"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": f"Lock acquired on `{args['resource']}`."}]}


def handle_release_lock(args):
    result = release_lock(args["session_id"], args["resource"])
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    return {"content": [{"type": "text", "text": "Lock released."}]}


def handle_list_leases(args):
    leases = list_all_leases()
    lines = ["## Active Leases\n"]
    lines.append(f"### Ports ({len(leases['ports'])} allocations)")
    for sid, alloc in leases["ports"].items():
        lines.append(f"- `{sid}`: ports {alloc['start']}-{alloc['end']}")
    lines.append(f"\n### Services ({len(leases['services'])} leases)")
    for key, svc in leases["services"].items():
        lines.append(f"- `{key}`: {svc['service_type']} ({svc['mode']})")
    lines.append(f"\n### Locks ({len(leases['locks'])} held)")
    for resource, lock in leases["locks"].items():
        lines.append(f"- `{resource}` → {lock['session_id']}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_check_conflicts(args):
    conflicts = check_conflicts(args.get("session_id"))
    if not conflicts:
        return {"content": [{"type": "text", "text": "No conflicts detected."}]}
    lines = [f"## Conflicts ({len(conflicts)} found)\n"]
    for c in conflicts:
        lines.append(f"- **{c['type']}**: session `{c['session']}` — {c.get('port', c.get('resource', ''))}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# --- MCP Protocol ---

def read_message():
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    content_length = int(headers.get("content-length", 0))
    if content_length == 0:
        return None
    return json.loads(sys.stdin.read(content_length))


def write_message(msg):
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def handle_request(msg):
    method = msg.get("method", "")
    id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "service-leasing-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "lease_port": handle_lease_port,
            "release_port": handle_release_port,
            "lease_service": handle_lease_service,
            "release_service": handle_release_service,
            "acquire_lock": handle_acquire_lock,
            "release_lock": handle_release_lock,
            "list_leases": handle_list_leases,
            "check_conflicts": handle_check_conflicts,
        }
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {name}"}}
        return {"jsonrpc": "2.0", "id": id, "result": handler(args)}
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": id, "result": {}}
    return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {method}"}}


def main():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break
            response = handle_request(msg)
            if response:
                write_message(response)
        except EOFError:
            break
        except Exception as e:
            sys.stderr.write(f"Service Leasing MCP error: {e}\n")


if __name__ == "__main__":
    main()
