#!/usr/bin/env python3
"""
Benchmark commands for platformctl.

Commands:
  benchmark list                List available benchmark tasks
  benchmark run <task-id>       Run a single benchmark task
  benchmark run-suite <repo>    Run all tasks for a repo
  benchmark results             Show latest results
  benchmark summarize <run-id>  Summarize a benchmark run
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BENCH_SCRIPTS_DIR = Path(os.environ.get("BENCH_SCRIPTS_DIR", "/opt/workstation/bench-scripts"))
BENCH_RESULTS_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", "/opt/workstation/bench-results"))
BENCH_TASKS_DIR = Path(os.environ.get("BENCH_TASKS_DIR", "/opt/workstation/bench-tasks"))


def cmd_benchmark(args):
    """Dispatch benchmark subcommands."""
    sub = getattr(args, "subcommand", None)
    if sub == "list":
        cmd_benchmark_list(args)
    elif sub == "run":
        cmd_benchmark_run(args)
    elif sub == "run-suite":
        cmd_benchmark_run_suite(args)
    elif sub == "results":
        cmd_benchmark_results(args)
    elif sub == "summarize":
        cmd_benchmark_summarize(args)
    else:
        print("Usage: platformctl benchmark {list|run|run-suite|results|summarize}")


def cmd_benchmark_list(args):
    """List benchmark tasks."""
    runner = BENCH_SCRIPTS_DIR / "run-benchmark.py"
    cmd = [sys.executable, str(runner), "list"]
    if hasattr(args, "repo") and args.repo:
        cmd.extend(["--repo", args.repo])
    if hasattr(args, "json") and args.json:
        cmd.append("--json")
    result = subprocess.run(cmd, capture_output=False)
    sys.exit(result.returncode)


def cmd_benchmark_run(args):
    """Run a single benchmark task."""
    runner = BENCH_SCRIPTS_DIR / "run-benchmark.py"
    task_id = args.task_id

    # Infer repo from task location
    repo = args.repo if hasattr(args, "repo") and args.repo else _find_task_repo(task_id)
    if not repo:
        print(f"ERROR: Could not find task '{task_id}'. Specify --repo.", file=sys.stderr)
        sys.exit(1)

    cmd = [sys.executable, str(runner), "run", "--repo", repo, "--task", task_id]
    result = subprocess.run(cmd, capture_output=False)
    sys.exit(result.returncode)


def cmd_benchmark_run_suite(args):
    """Run all tasks for a repo."""
    runner = BENCH_SCRIPTS_DIR / "run-benchmark.py"
    cmd = [sys.executable, str(runner), "run-suite", "--repo", args.repo]
    if hasattr(args, "max_parallel") and args.max_parallel:
        cmd.extend(["--max-parallel", str(args.max_parallel)])
    result = subprocess.run(cmd, capture_output=False)
    sys.exit(result.returncode)


def cmd_benchmark_results(args):
    """Show latest benchmark results."""
    if not BENCH_RESULTS_DIR.exists():
        print("No benchmark results found.")
        return

    runs = sorted([d for d in BENCH_RESULTS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()])
    if not runs:
        print("No benchmark runs found.")
        return

    if hasattr(args, "json") and args.json:
        all_results = []
        for run_dir in runs[-5:]:  # last 5 runs
            agg_file = run_dir / "aggregate.json"
            if agg_file.exists():
                with open(agg_file) as f:
                    all_results.append(json.loads(f.read()))
        print(json.dumps(all_results, indent=2))
        return

    print(f"{'Run ID':<20} {'Tasks':<8} {'Passed':<8} {'Failed':<8} {'Review':<8}")
    print("-" * 60)
    for run_dir in runs[-10:]:
        agg_file = run_dir / "aggregate.json"
        if agg_file.exists():
            with open(agg_file) as f:
                agg = json.loads(f.read())
            print(f"{run_dir.name:<20} {agg.get('total_tasks', '?'):<8} {agg.get('passed', '?'):<8} {agg.get('failed', '?'):<8} {agg.get('needs_review', '?'):<8}")
        else:
            # Count result files
            task_dirs = [d for d in run_dir.iterdir() if d.is_dir()]
            print(f"{run_dir.name:<20} {len(task_dirs):<8} {'?':<8} {'?':<8} {'?':<8}")


def cmd_benchmark_summarize(args):
    """Summarize a benchmark run."""
    summarizer = BENCH_SCRIPTS_DIR / "summarize-results.py"
    cmd = [sys.executable, str(summarizer)]
    if hasattr(args, "run_id") and args.run_id:
        cmd.append(args.run_id)
    else:
        cmd.append("--latest")
    result = subprocess.run(cmd, capture_output=False)
    sys.exit(result.returncode)


def _find_task_repo(task_id: str) -> str | None:
    """Find which repo a task belongs to."""
    if not BENCH_TASKS_DIR.exists():
        return None
    for repo_dir in BENCH_TASKS_DIR.iterdir():
        if repo_dir.is_dir() and (repo_dir / task_id / "task.yaml").exists():
            return repo_dir.name
    return None


def register_benchmark_parser(subparsers):
    """Register benchmark subcommands on the main argparse parser."""
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark management")
    bench_sub = bench_parser.add_subparsers(dest="subcommand")

    # list
    list_p = bench_sub.add_parser("list", help="List benchmark tasks")
    list_p.add_argument("--repo", help="Filter by repo")
    list_p.add_argument("--json", action="store_true")

    # run
    run_p = bench_sub.add_parser("run", help="Run a single task")
    run_p.add_argument("task_id", help="Task ID")
    run_p.add_argument("--repo", help="Repository name")

    # run-suite
    suite_p = bench_sub.add_parser("run-suite", help="Run all tasks for a repo")
    suite_p.add_argument("repo", help="Repository name")
    suite_p.add_argument("--max-parallel", type=int, default=1)

    # results
    results_p = bench_sub.add_parser("results", help="Show latest results")
    results_p.add_argument("--json", action="store_true")

    # summarize
    summarize_p = bench_sub.add_parser("summarize", help="Summarize a run")
    summarize_p.add_argument("run_id", nargs="?", help="Run ID (default: latest)")

    return bench_parser
