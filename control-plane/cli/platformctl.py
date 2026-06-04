#!/usr/bin/env python3
"""
platformctl — CLI for the multi-agent workstation control plane.

Commands:
  session list         List all active sessions
  session create       Create a new session
  session destroy      Destroy a session
  session inspect      Show session details
  session pause        Pause a session
  session resume       Resume a session
  context show         Show current context for a session
  health               Show system health (services, resources)
  logs                 Show recent logs
  models list          List configured model providers
  models status        Check model provider health
  knowledge list       List knowledge entries
  knowledge activate   Activate knowledge for a context
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
OPENHANDS_URL = os.environ.get("OPENHANDS_URL", "http://localhost:3000")
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:9876")
REPOS_DIR = Path("/opt/workstation/repos")


def cmd_session_list(args):
    """List all active sessions."""
    sessions = []
    if SESSIONS_DIR.exists():
        for d in sorted(SESSIONS_DIR.iterdir()):
            meta_file = d / "session.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                sessions.append(meta)

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
    session_id = args.name or f"session-{int(time.time())}"
    repo_path = args.repo or str(REPOS_DIR / "example-react-app")
    branch = args.branch or f"{session_id}-branch"

    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "context").mkdir(exist_ok=True)
    (session_dir / "events").mkdir(exist_ok=True)

    # Create git worktree if repo exists
    worktree_path = str(REPOS_DIR / f"worktree-{session_id}")
    if Path(repo_path).exists() and Path(repo_path / Path(".git")).exists():
        result = subprocess.run(
            ["git", "worktree", "add", worktree_path, "-b", branch],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Branch might exist, try without -b
            subprocess.run(
                ["git", "worktree", "add", worktree_path, branch],
                cwd=repo_path, capture_output=True, text=True,
            )

    meta = {
        "id": session_id,
        "repo_path": repo_path,
        "worktree_path": worktree_path,
        "branch": branch,
        "port_range": args.ports or "",
        "browser_profile": args.profile or session_id,
        "tmux_session": f"agent-{session_id}",
        "status": "active",
        "task": args.task or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(session_dir / "session.json", "w") as f:
        json.dump(meta, f, indent=2)

    if args.json:
        print(json.dumps(meta, indent=2))
    else:
        print(f"Created session: {session_id}")
        print(f"  Branch: {branch}")
        print(f"  Worktree: {worktree_path}")
        print(f"  Ports: {meta['port_range'] or 'auto'}")


def cmd_session_destroy(args):
    """Destroy a session."""
    session_id = args.name
    session_dir = SESSIONS_DIR / session_id

    if not session_dir.exists():
        print(f"Session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    meta_file = session_dir / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        worktree_path = meta.get("worktree_path", "")
        repo_path = meta.get("repo_path", "")

        # Remove worktree
        if worktree_path and Path(worktree_path).exists():
            subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                cwd=repo_path, capture_output=True,
            )

    # Remove session directory
    import shutil
    shutil.rmtree(session_dir)
    print(f"Destroyed session: {session_id}")


def cmd_session_inspect(args):
    """Show session details."""
    session_id = args.name
    session_dir = SESSIONS_DIR / session_id

    if not session_dir.exists():
        print(f"Session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    meta = json.loads((session_dir / "session.json").read_text())

    # Gather context info
    ui_ctx = session_dir / "context" / "latest-ui-context.md"
    ed_ctx = session_dir / "context" / "latest-editor-context.md"
    term_ctx = session_dir / "context" / "latest-terminal-context.md"

    meta["context"] = {
        "ui": ui_ctx.read_text()[:200] if ui_ctx.exists() else None,
        "editor": ed_ctx.read_text()[:200] if ed_ctx.exists() else None,
        "terminal": term_ctx.read_text()[:200] if term_ctx.exists() else None,
    }

    if args.json:
        print(json.dumps(meta, indent=2))
    else:
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
            val = meta["context"].get(ctx_type)
            if val:
                print(f"  Latest {ctx_type} context: {val[:100]}...")
            else:
                print(f"  Latest {ctx_type} context: (none)")


def cmd_context_show(args):
    """Show current context for a session."""
    session_id = args.session
    session_dir = SESSIONS_DIR / session_id

    if not session_dir.exists():
        print(f"Session '{session_id}' not found.", file=sys.stderr)
        sys.exit(1)

    context_dir = session_dir / "context"
    result = {}

    for ctx_file in ["latest-ui-context.md", "latest-editor-context.md", "latest-terminal-context.md"]:
        path = context_dir / ctx_file
        if path.exists():
            result[ctx_file] = path.read_text()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
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

    # LiteLLM
    try:
        req = urllib.request.urlopen(f"{LITELLM_URL}/health/liveliness", timeout=5)
        checks["litellm"] = {"status": "healthy", "url": LITELLM_URL}
    except Exception as e:
        checks["litellm"] = {"status": "unhealthy", "error": str(e)}

    # OpenHands
    try:
        req = urllib.request.urlopen(OPENHANDS_URL, timeout=5)
        checks["openhands"] = {"status": "healthy", "url": OPENHANDS_URL}
    except Exception as e:
        checks["openhands"] = {"status": "unhealthy", "error": str(e)}

    # Bridge
    try:
        req = urllib.request.urlopen(f"{BRIDGE_URL}/sessions", timeout=5)
        checks["bridge"] = {"status": "healthy", "url": BRIDGE_URL}
    except Exception as e:
        checks["bridge"] = {"status": "unhealthy", "error": str(e)}

    # System resources
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

    # Docker containers
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

    # Active sessions count
    session_count = 0
    if SESSIONS_DIR.exists():
        session_count = sum(1 for d in SESSIONS_DIR.iterdir() if (d / "session.json").exists())
    checks["sessions"] = {"active": session_count}

    if args.json:
        print(json.dumps(checks, indent=2))
    else:
        print("=== System Health ===")
        for svc in ["litellm", "openhands", "bridge"]:
            status = checks[svc].get("status", "?")
            icon = "UP" if status == "healthy" else "DOWN"
            print(f"  {svc:<12} {icon}")

        print(f"\n=== Resources ===")
        if "percent" in checks.get("disk", {}):
            print(f"  Disk: {checks['disk']['used']} used / {checks['disk']['available']} free ({checks['disk']['percent']})")
        if "total" in checks.get("memory", {}):
            print(f"  RAM:  {checks['memory']['used']} used / {checks['memory']['available']} free (of {checks['memory']['total']})")

        print(f"\n=== Docker ===")
        for c in checks.get("docker", []):
            print(f"  {c['name']:<30} {c['status']}")

        print(f"\n=== Sessions ===")
        print(f"  Active: {checks['sessions']['active']}")


def cmd_logs(args):
    """Show recent logs."""
    lines = args.lines or 50
    logs = {}

    # LiteLLM logs
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), "litellm"],
            capture_output=True, text=True,
        )
        logs["litellm"] = result.stdout[-2000:] + result.stderr[-2000:]
    except Exception:
        logs["litellm"] = ""

    # Bridge events
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


def cmd_models_list(args):
    """List configured model providers."""
    import urllib.request

    try:
        req = urllib.request.urlopen(f"{LITELLM_URL}/models", timeout=5)
        data = json.loads(req.read())
        models = data.get("data", [])
    except Exception:
        models = []

    # Also read config file
    config_path = Path("/opt/workstation/config/litellm_config.yaml")
    config_models = []
    if config_path.exists():
        import yaml
        try:
            config = yaml.safe_load(config_path.read_text())
            config_models = config.get("model_list", [])
        except Exception:
            pass

    if args.json:
        print(json.dumps({"live": models, "config": config_models}, indent=2))
    else:
        print("=== Configured Models ===")
        if config_models:
            for m in config_models:
                name = m.get("model_name", "?")
                params = m.get("litellm_params", {})
                model = params.get("model", "?")
                print(f"  {name:<25} → {model}")
        elif models:
            for m in models:
                print(f"  {m.get('id', '?')}")
        else:
            print("  No models found. Check LiteLLM config.")


def cmd_knowledge_list(args):
    """List knowledge entries."""
    entries = []
    if KNOWLEDGE_DIR.exists():
        import yaml
        for f in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
            try:
                entry = yaml.safe_load(f.read_text())
                if isinstance(entry, dict):
                    entries.append(entry)
            except Exception:
                continue

    if args.json:
        print(json.dumps(entries, indent=2))
    else:
        if not entries:
            print("No knowledge entries found.")
            return
        print(f"{'ID':<20} {'Confidence':<12} {'Description'}")
        print("-" * 70)
        for e in entries:
            print(f"{e.get('id', '?'):<20} {e.get('confidence', '-'):<12} {e.get('description', '-')[:40]}")


def cmd_doctor(args):
    """Run system diagnostics."""
    import urllib.request
    print("=== platformctl doctor ===\n")
    issues = []

    # Check services
    services = {
        "LiteLLM": f"{LITELLM_URL}/health/liveliness",
        "OpenHands": OPENHANDS_URL,
        "UI Bridge": f"http://localhost:9876/sessions",
        "Control Plane": "http://localhost:9877/api/health",
    }
    for name, url in services.items():
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"  [OK] {name}")
        except Exception as e:
            print(f"  [!!] {name} — {str(e)[:60]}")
            issues.append(f"{name} unreachable")

    # Check directories
    print()
    dirs = [SESSIONS_DIR, KNOWLEDGE_DIR, Path("/opt/workstation/repos"), Path("/opt/workstation/backups")]
    for d in dirs:
        if d.exists():
            print(f"  [OK] {d}")
        else:
            print(f"  [!!] {d} — MISSING")
            issues.append(f"Directory {d} missing")

    # Check Docker
    print()
    try:
        result = subprocess.run(["docker", "ps", "--format", "{{.Names}}:{{.Status}}"], capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            if line:
                print(f"  [OK] container: {line}")
    except Exception:
        print("  [!!] Docker not available")
        issues.append("Docker unavailable")

    # Check disk space
    print()
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        parts = result.stdout.strip().split("\n")[-1].split()
        pct = int(parts[4].replace("%", ""))
        if pct > 90:
            print(f"  [!!] Disk: {parts[4]} used — LOW SPACE")
            issues.append("Low disk space")
        else:
            print(f"  [OK] Disk: {parts[4]} used")
    except Exception:
        pass

    print(f"\n{'='*40}")
    if issues:
        print(f"  {len(issues)} issue(s) found:")
        for i in issues:
            print(f"    - {i}")
    else:
        print("  All checks passed. System healthy.")


def cmd_backup(args):
    """Backup workstation state."""
    backup_dir = Path("/opt/workstation/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"backup-{timestamp}.tar.gz"

    targets = [
        "/opt/workstation/sessions",
        "/opt/workstation/knowledge",
        "/opt/workstation/config",
    ]
    existing = [t for t in targets if Path(t).exists()]

    result = subprocess.run(
        ["tar", "czf", str(backup_path)] + existing,
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        size = backup_path.stat().st_size
        print(f"Backup created: {backup_path} ({size // 1024}KB)")
    else:
        print(f"Backup failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def cmd_restore(args):
    """Restore from backup."""
    backup_file = args.file
    if not Path(backup_file).exists():
        print(f"Backup file not found: {backup_file}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["tar", "xzf", backup_file, "-C", "/"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Restored from: {backup_file}")
    else:
        print(f"Restore failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def cmd_task(args):
    """Create a task with specified execution mode."""
    if args.subcommand != "create":
        print("Usage: platformctl task create --session <id> --mode <mode> --instruction <text>")
        return

    session_id = args.session
    mode = args.mode
    instruction = args.instruction

    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        print(f"Session not found: {session_id}", file=sys.stderr)
        sys.exit(1)

    config_file = session_dir / "config.json"
    if not config_file.exists():
        print(f"Session has no config: {session_id}", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_file.read_text())

    if mode == "fork-and-prove":
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from executors.fork_and_prove import ForkAndProveOrchestrator
        orchestrator = ForkAndProveOrchestrator(session_id)
        result = orchestrator.run(instruction, config.get("worktree", ""), config.get("branch", ""))
        if hasattr(args, "json") and args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Fork-and-prove completed:")
            print(f"  Candidates generated: {result.get('candidates_generated', 0)}")
            print(f"  Candidates implemented: {result.get('candidates_implemented', 0)}")
            print(f"  Duration: {result.get('duration_seconds', 0):.1f}s")
            print(f"  Report: {result.get('comparison_report', '')}")
    else:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from executors.direct_executor import DirectExecutor
        from executors.base import TaskPacket
        import uuid
        executor = DirectExecutor()
        packet = TaskPacket(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            instruction=instruction,
            worktree_path=config.get("worktree", ""),
            branch=config.get("branch", ""),
        )
        result = executor.run_task(session_id, packet)
        if hasattr(args, "json") and args.json:
            print(json.dumps({"status": result.status, "commit": result.commit_sha, "files": result.files_edited}, indent=2))
        else:
            print(f"Task {result.status}: {result.commit_sha or 'no commit'}")
            if result.files_edited:
                for f in result.files_edited:
                    print(f"  edited: {f}")


def cmd_fork(args):
    """Fork-and-prove management commands."""
    if not hasattr(args, "subcommand") or not args.subcommand:
        print("Usage: platformctl fork [list|compare|approve|reject]")
        return

    if args.subcommand == "list":
        session_id = args.session
        candidates_path = SESSIONS_DIR / session_id / "fork-and-prove" / "candidates.json"
        if not candidates_path.exists():
            print("No fork-and-prove candidates found.")
            return
        candidates = json.loads(candidates_path.read_text())
        if hasattr(args, "json") and args.json:
            print(json.dumps(candidates, indent=2))
        else:
            for c in candidates:
                selected = "[SELECTED]" if c.get("selected_for_implementation") else ""
                review = c.get("review_status", "")
                print(f"  {c['candidate_id']}: {c['title']} (score={c['score']:.3f}) {selected} {review}")

    elif args.subcommand == "compare":
        session_id = args.session
        report_path = SESSIONS_DIR / session_id / "fork-and-prove" / "comparison.md"
        if not report_path.exists():
            print("No comparison report found.")
            return
        print(report_path.read_text())

    elif args.subcommand in ("approve", "reject"):
        session_id = args.session
        candidate_id = args.candidate_id
        candidates_path = SESSIONS_DIR / session_id / "fork-and-prove" / "candidates.json"
        if not candidates_path.exists():
            print("No candidates found.", file=sys.stderr)
            sys.exit(1)
        candidates = json.loads(candidates_path.read_text())
        found = False
        for c in candidates:
            if c["candidate_id"] == candidate_id:
                c["review_status"] = "approved" if args.subcommand == "approve" else "rejected"
                c["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if not found:
            print(f"Candidate not found: {candidate_id}", file=sys.stderr)
            sys.exit(1)
        candidates_path.write_text(json.dumps(candidates, indent=2))
        print(f"Candidate {candidate_id}: {args.subcommand}d")


def cmd_policy(args):
    """Policy management commands."""
    if not hasattr(args, "subcommand") or args.subcommand != "show":
        print("Usage: platformctl policy show <name>")
        return

    name = args.name
    policy_path = Path(__file__).parent.parent / "policies" / f"{name}.yaml"
    if not policy_path.exists():
        print(f"Policy not found: {name}", file=sys.stderr)
        sys.exit(1)
    print(policy_path.read_text())


def main():
    parser = argparse.ArgumentParser(prog="platformctl", description="Workstation control plane CLI")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    subparsers = parser.add_subparsers(dest="command")

    # session
    session_parser = subparsers.add_parser("session", help="Session management")
    session_sub = session_parser.add_subparsers(dest="subcommand")

    list_p = session_sub.add_parser("list", help="List sessions")
    list_p.add_argument("--json", action="store_true")

    create_p = session_sub.add_parser("create", help="Create session")
    create_p.add_argument("--name", help="Session ID")
    create_p.add_argument("--repo", help="Repo path")
    create_p.add_argument("--branch", help="Branch name")
    create_p.add_argument("--ports", help="Port range (e.g., 5180-5189)")
    create_p.add_argument("--profile", help="Browser profile name")
    create_p.add_argument("--task", help="Task description")
    create_p.add_argument("--json", action="store_true")

    destroy_p = session_sub.add_parser("destroy", help="Destroy session")
    destroy_p.add_argument("name", help="Session ID")

    inspect_p = session_sub.add_parser("inspect", help="Inspect session")
    inspect_p.add_argument("name", help="Session ID")
    inspect_p.add_argument("--json", action="store_true")

    # context
    context_parser = subparsers.add_parser("context", help="Context management")
    context_sub = context_parser.add_subparsers(dest="subcommand")
    show_p = context_sub.add_parser("show", help="Show context")
    show_p.add_argument("session", help="Session ID")
    show_p.add_argument("--json", action="store_true")

    # health
    health_parser = subparsers.add_parser("health", help="System health")
    health_parser.add_argument("--json", action="store_true")

    # logs
    logs_parser = subparsers.add_parser("logs", help="View logs")
    logs_parser.add_argument("--service", help="Service name (litellm, bridge)")
    logs_parser.add_argument("--lines", type=int, default=50)
    logs_parser.add_argument("--json", action="store_true")

    # models
    models_parser = subparsers.add_parser("models", help="Model providers")
    models_sub = models_parser.add_subparsers(dest="subcommand")
    models_sub.add_parser("list", help="List models").add_argument("--json", action="store_true")
    models_sub.add_parser("status", help="Model status").add_argument("--json", action="store_true")

    # knowledge
    knowledge_parser = subparsers.add_parser("knowledge", help="Knowledge management")
    knowledge_sub = knowledge_parser.add_subparsers(dest="subcommand")
    knowledge_sub.add_parser("list", help="List entries").add_argument("--json", action="store_true")

    # task
    task_parser = subparsers.add_parser("task", help="Task management")
    task_sub = task_parser.add_subparsers(dest="subcommand")
    task_create_p = task_sub.add_parser("create", help="Create task")
    task_create_p.add_argument("--session", required=True, help="Session ID")
    task_create_p.add_argument("--mode", choices=["safe", "review-required", "full-autonomy-branch", "fork-and-prove"], default="safe")
    task_create_p.add_argument("--instruction", required=True, help="Task instruction")
    task_create_p.add_argument("--json", action="store_true")

    # fork
    fork_parser = subparsers.add_parser("fork", help="Fork-and-prove management")
    fork_sub = fork_parser.add_subparsers(dest="subcommand")

    fork_list_p = fork_sub.add_parser("list", help="List fork candidates")
    fork_list_p.add_argument("session", help="Parent session ID")
    fork_list_p.add_argument("--json", action="store_true")

    fork_compare_p = fork_sub.add_parser("compare", help="Show comparison report")
    fork_compare_p.add_argument("session", help="Parent session ID")

    fork_approve_p = fork_sub.add_parser("approve", help="Approve candidate")
    fork_approve_p.add_argument("candidate_id", help="Candidate ID (e.g. candidate-a)")
    fork_approve_p.add_argument("--session", required=True, help="Parent session ID")

    fork_reject_p = fork_sub.add_parser("reject", help="Reject candidate")
    fork_reject_p.add_argument("candidate_id", help="Candidate ID (e.g. candidate-a)")
    fork_reject_p.add_argument("--session", required=True, help="Parent session ID")

    # policy
    policy_parser = subparsers.add_parser("policy", help="Policy management")
    policy_sub = policy_parser.add_subparsers(dest="subcommand")
    policy_show_p = policy_sub.add_parser("show", help="Show a policy")
    policy_show_p.add_argument("name", help="Policy name (e.g. full-autonomy-branch)")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark management")
    bench_sub = bench_parser.add_subparsers(dest="subcommand")
    bench_list_p = bench_sub.add_parser("list", help="List benchmark tasks")
    bench_list_p.add_argument("--repo", help="Filter by repo")
    bench_list_p.add_argument("--json", action="store_true")
    bench_run_p = bench_sub.add_parser("run", help="Run a single task")
    bench_run_p.add_argument("task_id", help="Task ID")
    bench_run_p.add_argument("--repo", help="Repository name")
    bench_suite_p = bench_sub.add_parser("run-suite", help="Run all tasks for a repo")
    bench_suite_p.add_argument("repo", help="Repository name")
    bench_suite_p.add_argument("--max-parallel", type=int, default=1)
    bench_results_p = bench_sub.add_parser("results", help="Show latest results")
    bench_results_p.add_argument("--json", action="store_true")
    bench_summarize_p = bench_sub.add_parser("summarize", help="Summarize a run")
    bench_summarize_p.add_argument("run_id", nargs="?", help="Run ID (default: latest)")

    # doctor
    subparsers.add_parser("doctor", help="Run system diagnostics")

    # backup
    subparsers.add_parser("backup", help="Backup workstation state")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("file", help="Backup file path")

    args = parser.parse_args()

    if args.command == "session":
        if args.subcommand == "list":
            cmd_session_list(args)
        elif args.subcommand == "create":
            cmd_session_create(args)
        elif args.subcommand == "destroy":
            cmd_session_destroy(args)
        elif args.subcommand == "inspect":
            cmd_session_inspect(args)
        else:
            session_parser.print_help()
    elif args.command == "context":
        if args.subcommand == "show":
            cmd_context_show(args)
        else:
            context_parser.print_help()
    elif args.command == "health":
        cmd_health(args)
    elif args.command == "logs":
        cmd_logs(args)
    elif args.command == "models":
        if args.subcommand in ("list", "status"):
            cmd_models_list(args)
        else:
            models_parser.print_help()
    elif args.command == "knowledge":
        if args.subcommand == "list":
            cmd_knowledge_list(args)
        else:
            knowledge_parser.print_help()
    elif args.command == "task":
        cmd_task(args)
    elif args.command == "fork":
        cmd_fork(args)
    elif args.command == "policy":
        cmd_policy(args)
    elif args.command == "benchmark":
        from benchmark_commands import cmd_benchmark
        cmd_benchmark(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "restore":
        cmd_restore(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
