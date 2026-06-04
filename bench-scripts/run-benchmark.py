#!/usr/bin/env python3
"""
run-benchmark.py — Benchmark runner for the AI coding workstation.

Usage:
  python3 run-benchmark.py list
  python3 run-benchmark.py run --repo cypress-realworld-app --task ui-tooltip-clipping
  python3 run-benchmark.py run-suite --repo cypress-realworld-app --max-parallel 3
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

BENCH_TASKS_DIR = Path(os.environ.get("BENCH_TASKS_DIR", "/opt/workstation/bench-tasks"))
BENCH_APPS_DIR = Path(os.environ.get("BENCH_APPS_DIR", "/opt/workstation/bench-apps"))
BENCH_RESULTS_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", "/opt/workstation/bench-results"))
SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
REPOS_DIR = Path(os.environ.get("REPOS_DIR", "/opt/workstation/repos"))
CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://localhost:9877")

# OpenHands port is auto-allocated — read from file if available
def get_openhands_port() -> int:
    port_file = Path("/opt/workstation/logs/openhands-port")
    if port_file.exists():
        try:
            return int(port_file.read_text().strip())
        except (ValueError, OSError):
            pass
    return 3010  # fallback default

OPENHANDS_URL = os.environ.get("OPENHANDS_URL", f"http://localhost:{get_openhands_port()}")

# Dev server configurations per repo
DEV_SERVER_CONFIG = {
    "cypress-realworld-app": {
        "install_cmd": "yarn install",
        "dev_cmd": "yarn dev",
        "port": 3000,
        "ready_pattern": "compiled successfully",
        "startup_timeout": 60,
    },
    "juice-shop": {
        "install_cmd": "npm install",
        "dev_cmd": "npm start",
        "port": 3000,
        "ready_pattern": "listening on",
        "startup_timeout": 60,
    },
    "todomvc": {
        "install_cmd": "npm install",
        "dev_cmd": "npx serve -l 8080",
        "port": 8080,
        "ready_pattern": "Accepting connections",
        "startup_timeout": 15,
    },
}


def open_browser(url: str):
    """Open a URL in Firefox on the server desktop."""
    display = os.environ.get("DISPLAY", ":10")
    xauth = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = xauth
    try:
        subprocess.Popen(
            ["firefox", "--new-tab", url],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  Browser opened: {url}")
    except FileNotFoundError:
        print(f"  Browser not available — open manually: {url}")


def start_dev_server(repo: str, worktree_path: str) -> Optional[subprocess.Popen]:
    """Start the dev server for a web app. Returns the process or None."""
    config = DEV_SERVER_CONFIG.get(repo)
    if not config:
        return None

    port = config["port"]
    dev_cmd = config["dev_cmd"]
    install_cmd = config.get("install_cmd")
    startup_timeout = config.get("startup_timeout", 60)

    # Check if port already in use
    check = subprocess.run(
        ["ss", "-tlnp"], capture_output=True, text=True
    )
    if f":{port} " in check.stdout:
        print(f"  Dev server already running on port {port}")
        return None

    # Install deps if needed
    if install_cmd:
        node_modules = Path(worktree_path) / "node_modules"
        if not node_modules.exists():
            print(f"  Installing dependencies: {install_cmd}")
            subprocess.run(
                install_cmd, shell=True, cwd=worktree_path,
                capture_output=True, text=True, timeout=300,
            )

    # Start dev server
    print(f"  Starting dev server: {dev_cmd} (port {port})")
    proc = subprocess.Popen(
        dev_cmd, shell=True, cwd=worktree_path,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for it to be ready
    import select
    start = time.time()
    while time.time() - start < startup_timeout:
        # Check if port is listening
        check = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        if f":{port} " in check.stdout:
            print(f"  Dev server ready on port {port}")
            return proc
        if proc.poll() is not None:
            print(f"  Dev server exited unexpectedly (code {proc.returncode})")
            return None
        time.sleep(2)

    print(f"  Dev server did not start within {startup_timeout}s (continuing anyway)")
    return proc


def stop_dev_server(proc: Optional[subprocess.Popen]):
    """Stop the dev server process."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def load_task(repo: str, task_id: str) -> dict:
    """Load a task definition from YAML."""
    task_path = BENCH_TASKS_DIR / repo / task_id / "task.yaml"
    if not task_path.exists():
        print(f"ERROR: Task not found: {task_path}", file=sys.stderr)
        sys.exit(1)
    with open(task_path) as f:
        return yaml.safe_load(f)


def list_tasks(repo: Optional[str] = None) -> list[dict]:
    """List all available benchmark tasks."""
    tasks = []
    search_dir = BENCH_TASKS_DIR / repo if repo else BENCH_TASKS_DIR
    if not search_dir.exists():
        return tasks

    for repo_dir in sorted(search_dir.iterdir() if not repo else [search_dir]):
        if not repo_dir.is_dir():
            continue
        for task_dir in sorted(repo_dir.iterdir()):
            task_file = task_dir / "task.yaml"
            if task_file.exists():
                with open(task_file) as f:
                    task = yaml.safe_load(f)
                    tasks.append(task)
    return tasks


def create_worktree(repo: str, task_id: str, run_id: str) -> str:
    """Create an isolated git worktree for the benchmark task."""
    repo_path = BENCH_APPS_DIR / repo
    branch_name = f"bench-{run_id}-{task_id}"
    worktree_path = REPOS_DIR / f"bench-{run_id}-{task_id}"

    if not repo_path.exists():
        print(f"ERROR: Repo not found at {repo_path}", file=sys.stderr)
        sys.exit(1)

    # Create worktree from current HEAD
    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch_name],
        cwd=str(repo_path),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Try without -b if branch exists
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            cwd=str(repo_path),
            capture_output=True, text=True,
        )

    return str(worktree_path)


def apply_seed_patch(worktree_path: str, repo: str, task_id: str) -> bool:
    """Apply the seed patch to introduce the bug."""
    patch_file = BENCH_TASKS_DIR / repo / task_id / "seed.patch"
    if not patch_file.exists():
        print(f"WARNING: No seed patch found for {task_id}")
        return True

    result = subprocess.run(
        ["git", "apply", "--check", str(patch_file)],
        cwd=worktree_path,
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        # Patch may not apply cleanly — try with --3way
        result = subprocess.run(
            ["git", "apply", "--3way", str(patch_file)],
            cwd=worktree_path,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"WARNING: Seed patch does not apply cleanly: {result.stderr}")
            return False

    # Apply for real
    subprocess.run(
        ["git", "apply", str(patch_file)],
        cwd=worktree_path,
        capture_output=True, text=True,
    )

    # Commit the seeded bug
    subprocess.run(["git", "add", "-A"], cwd=worktree_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Seed bug: {task_id}"],
        cwd=worktree_path, capture_output=True,
    )

    return True


def create_session(task: dict, worktree_path: str, run_id: str) -> dict:
    """Create a platform session for the benchmark task."""
    import urllib.request

    session_data = {
        "name": f"bench-{run_id}-{task['id']}",
        "repo": worktree_path,
        "branch": f"bench-{run_id}-{task['id']}",
        "task": task["instruction"][:200],
    }

    try:
        req = urllib.request.Request(
            f"{CONTROL_PLANE_URL}/api/sessions",
            data=json.dumps(session_data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"WARNING: Could not create session via API: {e}")
        # Fallback: create session directory manually
        session_id = session_data["name"]
        session_dir = SESSIONS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context").mkdir(exist_ok=True)
        (session_dir / "events").mkdir(exist_ok=True)

        meta = {
            "id": session_id,
            "repo_path": worktree_path,
            "worktree_path": worktree_path,
            "branch": session_data["branch"],
            "status": "active",
            "task": session_data["task"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(session_dir / "session.json", "w") as f:
            json.dump(meta, f, indent=2)
        return meta


def inject_context(task: dict, session_id: str, worktree_path: str):
    """Inject context (UI/editor/terminal) for the task."""
    context_source = task.get("context_source", "editor")
    session_dir = SESSIONS_DIR / session_id / "context"
    session_dir.mkdir(parents=True, exist_ok=True)

    context_content = f"""# Benchmark Task Context
Task: {task['title']}
Source: {context_source}
Instruction: {task['instruction']}
Working directory: {worktree_path}
"""

    if context_source == "browser":
        (session_dir / "latest-ui-context.md").write_text(context_content)
    elif context_source == "editor":
        (session_dir / "latest-editor-context.md").write_text(context_content)
    elif context_source == "terminal":
        (session_dir / "latest-terminal-context.md").write_text(context_content)


def run_validation(task: dict, worktree_path: str) -> tuple[bool, list[str]]:
    """Run validation commands and return (passed, output_lines)."""
    commands = task.get("validation_commands", [])
    outputs = []
    all_passed = True

    for cmd in commands:
        result = subprocess.run(
            cmd, shell=True, cwd=worktree_path,
            capture_output=True, text=True, timeout=120,
        )
        outputs.append(f"$ {cmd}")
        outputs.append(result.stdout[-500:] if result.stdout else "")
        if result.returncode != 0:
            outputs.append(f"FAILED (exit {result.returncode}): {result.stderr[-300:]}")
            all_passed = False
        else:
            outputs.append("PASSED")

    return all_passed, outputs


def check_expected_files(task: dict, worktree_path: str) -> tuple[bool, list[str], list[str]]:
    """Check if expected files were modified."""
    expected = set(task.get("expected_files", []))
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1"],
        cwd=worktree_path, capture_output=True, text=True,
    )
    changed = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

    expected_touched = expected.issubset(changed)
    return expected_touched, sorted(changed), sorted(expected)


def get_git_diff(worktree_path: str) -> str:
    """Get the git diff of changes."""
    result = subprocess.run(
        ["git", "diff", "HEAD~1"],
        cwd=worktree_path, capture_output=True, text=True,
    )
    return result.stdout


def run_task(repo: str, task_id: str, run_id: Optional[str] = None) -> dict:
    """Run a single benchmark task end-to-end."""
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    task = load_task(repo, task_id)

    print(f"\n{'='*60}")
    print(f"  Benchmark: {task['title']}")
    print(f"  Repo: {repo} | Task: {task_id} | Difficulty: {task.get('difficulty', '?')}")
    print(f"{'='*60}\n")

    start_time = time.time()

    # 1. Create worktree
    print("[1/6] Creating worktree...")
    worktree_path = create_worktree(repo, task_id, run_id)
    print(f"  Worktree: {worktree_path}")

    # 2. Apply seed patch
    print("[2/6] Applying seed patch...")
    patch_ok = apply_seed_patch(worktree_path, repo, task_id)
    if not patch_ok:
        print("  WARNING: Seed patch did not apply cleanly")

    # 3. Create session
    print("[3/6] Creating platform session...")
    session = create_session(task, worktree_path, run_id)
    session_id = session.get("id", f"bench-{run_id}-{task_id}")
    print(f"  Session: {session_id}")

    # 4. Start dev server and open browser (for web apps)
    print("[4/8] Starting dev server...")
    dev_server_proc = start_dev_server(repo, worktree_path)
    server_config = DEV_SERVER_CONFIG.get(repo)
    app_url = None
    if server_config:
        app_url = f"http://localhost:{server_config['port']}"
        print(f"  App URL: {app_url}")

    # 5. Open browser if web app
    print("[5/8] Opening browser...")
    if app_url and task.get("context_source") in ("browser", "editor"):
        open_browser(app_url)
    else:
        print("  Not a browser task — skipping")

    # 6. Inject context
    print("[6/8] Injecting context...")
    inject_context(task, session_id, worktree_path)
    print(f"  Context source: {task.get('context_source', 'editor')}")

    # 7. Submit task to executor
    print("[7/8] Submitting task to executor...")
    # In a full implementation, this would call the Direct Executor or OpenHands
    # For now, we log the submission and mark as needs_review
    print(f"  Instruction: {task['instruction'][:100]}...")
    print("  [Awaiting autonomous executor — manual review needed]")

    # 8. Collect results
    print("[8/8] Collecting results...")
    runtime = time.time() - start_time

    # Get current state (after executor would have run)
    result_data = {
        "task_id": task_id,
        "repo": repo,
        "session_id": session_id,
        "branch": f"bench-{run_id}-{task_id}",
        "status": "needs_review",
        "validation_passed": False,
        "expected_files_touched": False,
        "changed_files": [],
        "expected_files": task.get("expected_files", []),
        "commands_run": task.get("validation_commands", []),
        "token_cost_usd": 0.0,
        "runtime_seconds": round(runtime, 2),
        "commit": "",
        "notes": "Awaiting autonomous executor. Validate manually or re-run after executor completes.",
    }

    # Write results
    result_dir = BENCH_RESULTS_DIR / run_id / task_id
    result_dir.mkdir(parents=True, exist_ok=True)

    with open(result_dir / "result.json", "w") as f:
        json.dump(result_data, f, indent=2)

    # Write timeline stub
    timeline_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "benchmark_task_submitted",
        "task_id": task_id,
        "session_id": session_id,
    }
    with open(result_dir / "timeline.jsonl", "w") as f:
        f.write(json.dumps(timeline_entry) + "\n")

    # Write summary
    summary = f"""# Benchmark Result: {task_id}

| Field | Value |
|-------|-------|
| Task | {task['title']} |
| Repo | {repo} |
| Status | {result_data['status']} |
| Runtime | {result_data['runtime_seconds']}s |
| Validation | {'PASSED' if result_data['validation_passed'] else 'PENDING'} |
| Expected Files | {', '.join(result_data['expected_files'])} |
| Session | {session_id} |
| Run ID | {run_id} |

## Instruction
{task['instruction']}

## Notes
{result_data['notes']}
"""
    with open(result_dir / "summary.md", "w") as f:
        f.write(summary)

    print(f"\n  Result: {result_dir / 'result.json'}")
    print(f"  Status: {result_data['status']}")
    print(f"  Runtime: {result_data['runtime_seconds']}s")

    # Cleanup: stop dev server
    stop_dev_server(dev_server_proc)

    return result_data


def cmd_list(args):
    """List available benchmark tasks."""
    tasks = list_tasks(args.repo if hasattr(args, "repo") else None)
    if not tasks:
        print("No benchmark tasks found.")
        print(f"  Tasks directory: {BENCH_TASKS_DIR}")
        return

    if hasattr(args, "json") and args.json:
        print(json.dumps(tasks, indent=2))
        return

    print(f"{'ID':<30} {'Category':<20} {'Difficulty':<12} {'Title'}")
    print("-" * 100)
    for t in tasks:
        print(f"{t.get('id', '?'):<30} {t.get('category', '-'):<20} {t.get('difficulty', '-'):<12} {t.get('title', '-')[:40]}")
    print(f"\nTotal: {len(tasks)} tasks")


def cmd_run(args):
    """Run a single benchmark task."""
    result = run_task(args.repo, args.task)
    return result


def cmd_run_suite(args):
    """Run all tasks for a repo."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tasks = list_tasks(args.repo)

    if not tasks:
        print(f"No tasks found for repo: {args.repo}")
        return

    max_parallel = getattr(args, "max_parallel", 1)
    print(f"Running {len(tasks)} tasks (max_parallel={max_parallel})")
    print(f"Run ID: {run_id}\n")

    results = []
    for task in tasks:
        result = run_task(args.repo, task["id"], run_id=run_id)
        results.append(result)

    # Write aggregate
    aggregate = {
        "run_id": run_id,
        "repo": args.repo,
        "total_tasks": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "needs_review": sum(1 for r in results if r["status"] == "needs_review"),
        "total_runtime": sum(r["runtime_seconds"] for r in results),
        "total_cost": sum(r["token_cost_usd"] for r in results),
    }

    agg_dir = BENCH_RESULTS_DIR / run_id
    agg_dir.mkdir(parents=True, exist_ok=True)
    with open(agg_dir / "aggregate.json", "w") as f:
        json.dump(aggregate, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  Suite Complete: {aggregate['total_tasks']} tasks")
    print(f"  Passed: {aggregate['passed']} | Failed: {aggregate['failed']} | Review: {aggregate['needs_review']}")
    print(f"  Runtime: {aggregate['total_runtime']:.1f}s | Cost: ${aggregate['total_cost']:.4f}")
    print(f"  Results: {agg_dir}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark runner for AI coding workstation")
    subparsers = parser.add_subparsers(dest="command")

    # list
    list_parser = subparsers.add_parser("list", help="List benchmark tasks")
    list_parser.add_argument("--repo", help="Filter by repo")
    list_parser.add_argument("--json", action="store_true", help="JSON output")

    # run
    run_parser = subparsers.add_parser("run", help="Run a single benchmark task")
    run_parser.add_argument("--repo", required=True, help="Repository name")
    run_parser.add_argument("--task", required=True, help="Task ID")

    # run-suite
    suite_parser = subparsers.add_parser("run-suite", help="Run all tasks for a repo")
    suite_parser.add_argument("--repo", required=True, help="Repository name")
    suite_parser.add_argument("--max-parallel", type=int, default=1, help="Max parallel tasks")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "run-suite":
        cmd_run_suite(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
