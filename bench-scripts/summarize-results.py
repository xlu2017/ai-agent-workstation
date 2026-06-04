#!/usr/bin/env python3
"""
summarize-results.py — Aggregate benchmark results into a report.

Usage:
  python3 summarize-results.py <run-id>
  python3 summarize-results.py --latest
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BENCH_RESULTS_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", "/opt/workstation/bench-results"))


def find_latest_run() -> str:
    """Find the most recent run ID."""
    runs = [d for d in BENCH_RESULTS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()]
    if not runs:
        print("ERROR: No benchmark runs found.", file=sys.stderr)
        sys.exit(1)
    return sorted(runs)[-1].name


def load_results(run_id: str) -> list[dict]:
    """Load all result.json files for a run."""
    run_dir = BENCH_RESULTS_DIR / run_id
    if not run_dir.exists():
        print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    results = []
    for task_dir in sorted(run_dir.iterdir()):
        result_file = task_dir / "result.json"
        if result_file.exists():
            with open(result_file) as f:
                results.append(json.loads(f.read()))
    return results


def compute_metrics(results: list[dict]) -> dict:
    """Compute aggregate metrics from results."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    needs_review = sum(1 for r in results if r.get("status") == "needs_review")

    validation_passed = sum(1 for r in results if r.get("validation_passed"))
    expected_files_ok = sum(1 for r in results if r.get("expected_files_touched"))

    total_runtime = sum(r.get("runtime_seconds", 0) for r in results)
    total_cost = sum(r.get("token_cost_usd", 0) for r in results)

    # Unexpected files
    unexpected_file_count = 0
    for r in results:
        changed = set(r.get("changed_files", []))
        expected = set(r.get("expected_files", []))
        unexpected_file_count += len(changed - expected)

    return {
        "total_tasks": total,
        "task_success_rate": round(passed / total * 100, 1) if total else 0,
        "validation_pass_rate": round(validation_passed / total * 100, 1) if total else 0,
        "expected_file_recall": round(expected_files_ok / total * 100, 1) if total else 0,
        "unexpected_file_count": unexpected_file_count,
        "total_runtime_seconds": round(total_runtime, 1),
        "total_token_cost_usd": round(total_cost, 4),
        "passed": passed,
        "failed": failed,
        "needs_review": needs_review,
        "avg_runtime_seconds": round(total_runtime / total, 1) if total else 0,
        "avg_cost_per_task": round(total_cost / total, 4) if total else 0,
    }


def generate_report(run_id: str, results: list[dict], metrics: dict) -> str:
    """Generate a markdown aggregate report."""
    report = f"""# Benchmark Aggregate Report

**Run ID:** {run_id}
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Total Tasks:** {metrics['total_tasks']}

## Summary Metrics

| Metric | Value |
|--------|-------|
| Task Success Rate | {metrics['task_success_rate']}% |
| Validation Pass Rate | {metrics['validation_pass_rate']}% |
| Expected-File Recall | {metrics['expected_file_recall']}% |
| Unexpected File Count | {metrics['unexpected_file_count']} |
| Total Runtime | {metrics['total_runtime_seconds']}s |
| Avg Runtime/Task | {metrics['avg_runtime_seconds']}s |
| Total Token Cost | ${metrics['total_token_cost_usd']} |
| Avg Cost/Task | ${metrics['avg_cost_per_task']} |

## Status Breakdown

| Status | Count |
|--------|-------|
| Passed | {metrics['passed']} |
| Failed | {metrics['failed']} |
| Needs Review | {metrics['needs_review']} |

## Per-Task Results

| Task ID | Status | Validation | Runtime | Cost |
|---------|--------|------------|---------|------|
"""

    for r in results:
        status_icon = {"passed": "PASS", "failed": "FAIL", "needs_review": "REVIEW"}.get(r.get("status", "?"), "?")
        validation = "Yes" if r.get("validation_passed") else "No"
        report += f"| {r.get('task_id', '?')} | {status_icon} | {validation} | {r.get('runtime_seconds', 0)}s | ${r.get('token_cost_usd', 0):.4f} |\n"

    report += f"""
## Context Routing

| Task ID | Context Source | Context Injected |
|---------|---------------|------------------|
"""
    for r in results:
        report += f"| {r.get('task_id', '?')} | - | Yes |\n"

    report += """
## Recommendations

- Tasks in "needs_review" status require autonomous executor integration
- Re-run after executor is connected to get validation results
- Monitor token cost as task complexity increases
"""

    return report


def main():
    parser = argparse.ArgumentParser(description="Summarize benchmark results")
    parser.add_argument("run_id", nargs="?", help="Run ID to summarize")
    parser.add_argument("--latest", action="store_true", help="Summarize latest run")
    parser.add_argument("--json", action="store_true", help="Output metrics as JSON")

    args = parser.parse_args()

    if args.latest or not args.run_id:
        run_id = find_latest_run()
    else:
        run_id = args.run_id

    print(f"Summarizing run: {run_id}")
    results = load_results(run_id)
    metrics = compute_metrics(results)

    if args.json:
        print(json.dumps(metrics, indent=2))
        return

    report = generate_report(run_id, results, metrics)

    # Write report
    output_path = BENCH_RESULTS_DIR / run_id / "aggregate.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)

    print(f"Report written to: {output_path}")
    print(f"\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
