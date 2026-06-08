#!/usr/bin/env python3
"""
platformctl — CLI for the multi-agent workstation control plane.

Session lifecycle logic is delegated to sessions.session_manager so CLI and API
share the same worktree/session behavior.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from sessions.session_manager import (
    SessionAlreadyExists,
    SessionCreateRequest,
    SessionNotFound,
    create_session,
    destroy_session,
    get_session_context,
    inspect_session,
    list_sessions,
)

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
OPENHANDS_URL = os.environ.get("OPENHANDS_URL", "http://localhost:3000")
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")


def cmd_session_list(args):
    """List all active sessions."""
    sessions = list_sessions()

    if args.json:
        print(json.dumps(sessions, indent=2))
        return

    if not sessions:
        print("No active sessions.")
        return

    print(f"{'ID':<20} {'Branch':<25} {'Ports':<12} {'Status':<10} {'Task'}")
    print("-" * 90)
    for s in sessions:
        print(f"{s.get('id', '?'):<20} {s.get('branch', '-'):<25} {s.get('port_range', '-'):<12} {s.get('status', '-'):<10} {s.get('task', '-')[:30]}")


def cmd_session_create(args):
    """Create a new session."""
    try:
        meta = create_session(
            SessionCreateRequest(
                name=args.name,
                repo=args.repo,
                branch=args.branch,
                ports=args.ports,
                profile=args.profile,
                task=args.task,
            )
        )
    except SessionAlreadyExists as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(meta, indent=2))
    else:
        print(f"Created session: {meta['id']}")
        print(f"  Branch: {meta['branch']}")
        print(f"  Worktree: {meta['worktree_path']}")
        print(f"  Ports: {meta['port_range'] or 'auto'}")


def cmd_session_destroy(args):
    """Destroy a session."""
    try:
        result = destroy_session(args.name)
    except SessionNotFound as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(f"Destroyed session: {result['session_id']}")


def cmd_session_inspect(args):
    """Show session details."""
    try:
        meta = inspect_session(args.name, context_limit=200)
    except SessionNotFound as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(meta, indent=2))
        return

    print(f"Session: {meta['id']}")
    print(f"  Status: {meta.get('status', '?')}")
    print(f"  Branch: {meta.get('branch', '-')}")
    print(f"  Repo: {meta.get('repo_path', '-')}")
    print(f"  Worktree: {meta.get('worktree_path', '-')}")
    print(f"  Ports: {meta.get('port_range', '-')}")
    print(f"  Task: {meta.get('task', '-')}")
    print(f"  Created: {meta.get('created_at', '-')}")
    print()
    for ctx_type in ("ui", "editor", "terminal"):
        val = meta.get("context", {}).get(ctx_type)
        if val:
            print(f"  Latest {ctx_type} context: {val[:100]}...")
        else:
            print(f"  Latest {ctx_type} context: (none)")


def cmd_context_show(args):
    """Show current context for a session."""
    try:
        result = get_session_context(args.session)["context"]
    except SessionNotFound as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    for name, content in result.items():
        print(f"=== {name} ===")
        print(content[:500])
        print()
    if not result:
        print("No context available for this session.")


def cmd_health(args):
    """Show system health."""
    import urllib.request

    checks = {}

    try:
        urllib.request.urlopen(f"{LITELLM_URL}/health/liveliness", timeout=5)
        checks["litellm"] = {"status": "healthy", "url": LITELLM_URL}
    except Exception as e:
        checks["litellm"] = {"status": "unhealthy", "error": str(e)}

    try:
        urllib.request.urlopen(OPENHANDS_URL, timeout=5)
        checks["openhands"] = {"status": "healthy", "url": OPENHANDS_URL}
    except Exception as e:
        checks["openhands"] = {"status": "unhealthy", "error": str(e)}

    try:
        urllib.request.urlopen(f"{BRIDGE_URL}/sessions", timeout=5)
        checks["bridge"] = {"status": "healthy", "url": BRIDGE_URL}
    except Exception as e:
        checks["bridge"] = {"status": "unhealthy", "error": str(e)}

    try:
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        disk_line = disk.stdout.strip().split("\n")[-1].split()
        checks["disk"] = {"used": disk_line[2], "available": disk_line[3], "percent": disk_line[4]}
    except Exception:
        checks["disk"] = {"status": "unknown"}

    try:
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True)
        mem_line = mem.stdout.strip().split("\n")[1].split()
        checks["memory"] = {"total": mem_line[1], "used": mem_line[2], "available": mem_line[6]}
    except Exception:
        checks["memory"] = {"status": "unknown"}

    try:
        docker = subprocess.run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], capture_output=True, text=True)
        containers = []
        for line in docker.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("\t")
                containers.append({"name": parts[0], "status": parts[1] if len(parts) > 1 else "?"})
        checks["docker"] = containers
    except Exception:
        checks["docker"] = []

    checks["sessions"] = {"active": len(list_sessions())}

    if args.json:
        print(json.dumps(checks, indent=2))
        return

    print("=== System Health ===")
    for svc in ["litellm", "openhands", "bridge"]:
        status = checks[svc].get("status", "?")
        icon = "UP" if status == "healthy" else "DOWN"
        print(f"  {svc:<12} {icon}")

    print("\n=== Resources ===")
    if "percent" in checks.get("disk", {}):
        print(f"  Disk: {checks['disk']['used']} used / {checks['disk']['available']} free ({checks['disk']['percent']})")
    if "total" in checks.get("memory", {}):
        print(f"  RAM:  {checks['memory']['used']} used / {checks['memory']['available']} free (of {checks['memory']['total']})")

    print("\n=== Docker ===")
    for c in checks.get("docker", []):
        print(f"  {c['name']:<30} {c['status']}")

    print("\n=== Sessions ===")
    print(f"  Active: {checks['sessions']['active']}")


def cmd_logs(args):
    """Show recent logs."""
    lines = args.lines or 50
    logs = {}

    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), "litellm"],
            capture_output=True, text=True,
        )
        logs["litellm"] = result.stdout[-2000:] + result.stderr[-2000:]
    except Exception:
        logs["litellm"] = ""

    events_log = Path("/opt/workstation/glue/ui-bridge/events.jsonl")
    if events_log.exists():
        log_lines = events_log.read_text().strip().split("\n")
        logs["bridge_events"] = log_lines[-lines:]

    if args.json:
        print(json.dumps(logs, indent=2))
    else:
        if args.service == "litellm" or not args.service:
            print("=== LiteLLM Logs ===")
            print(logs.get("litellm", "(none)")[:2000])
        if args.service == "bridge" or not args.service:
            print("\n=== Bridge Events ===")
            for line in logs.get("bridge_events", [])[-10:]:
                print(f"  {line[:120]}")


# Remaining CLI commands were intentionally removed from this cleanup patch if
# they existed only in stale duplicated scaffolding. Add new commands back by
# delegating to shared control-plane modules instead of embedding service logic.

def build_parser():
    parser = argparse.ArgumentParser(description="Workstation control-plane CLI")
    sub = parser.add_subparsers(dest="command")

    session = sub.add_parser("session")
    session_sub = session.add_subparsers(dest="session_command")

    session_list = session_sub.add_parser("list")
    session_list.add_argument("--json", action="store_true")
    session_list.set_defaults(func=cmd_session_list)

    session_create = session_sub.add_parser("create")
    session_create.add_argument("--name")
    session_create.add_argument("--repo")
    session_create.add_argument("--branch")
    session_create.add_argument("--ports")
    session_create.add_argument("--profile")
    session_create.add_argument("--task")
    session_create.add_argument("--json", action="store_true")
    session_create.set_defaults(func=cmd_session_create)

    session_destroy = session_sub.add_parser("destroy")
    session_destroy.add_argument("name")
    session_destroy.set_defaults(func=cmd_session_destroy)

    session_inspect = session_sub.add_parser("inspect")
    session_inspect.add_argument("name")
    session_inspect.add_argument("--json", action="store_true")
    session_inspect.set_defaults(func=cmd_session_inspect)

    context = sub.add_parser("context")
    context_sub = context.add_subparsers(dest="context_command")
    context_show = context_sub.add_parser("show")
    context_show.add_argument("session")
    context_show.add_argument("--json", action="store_true")
    context_show.set_defaults(func=cmd_context_show)

    health = sub.add_parser("health")
    health.add_argument("--json", action="store_true")
    health.set_defaults(func=cmd_health)

    logs = sub.add_parser("logs")
    logs.add_argument("--service")
    logs.add_argument("--lines", type=int)
    logs.add_argument("--json", action="store_true")
    logs.set_defaults(func=cmd_logs)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
