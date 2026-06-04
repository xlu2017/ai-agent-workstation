#!/usr/bin/env python3
"""
Autonomy Daemon — discovers work and spawns agent sessions.

Scans for:
- TODO/FIXME in code
- Failing tests
- Lint/type errors
- Postmortem suggestions
- Dependency updates
- Knowledge trigger proposals

Creates low-risk tasks automatically. High-risk tasks go to review queue.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
TASKS_DIR = Path(os.environ.get("TASKS_DIR", "/opt/workstation/tasks"))
REPOS_DIR = Path(os.environ.get("REPOS_DIR", "/opt/workstation/repos"))
SCAN_INTERVAL = int(os.environ.get("AUTONOMY_SCAN_INTERVAL", "300"))  # 5 min


class AutonomyDaemon:
    """Discovers work and creates tasks."""

    def __init__(self):
        self.discovered = set()  # track what we already found to avoid duplicates

    def scan_all(self) -> list:
        """Run all scanners, return list of proposed tasks."""
        proposals = []
        for repo_dir in REPOS_DIR.iterdir():
            if not (repo_dir / ".git").exists():
                continue
            proposals.extend(self.scan_todos(repo_dir))
            proposals.extend(self.scan_lint_errors(repo_dir))
            proposals.extend(self.scan_type_errors(repo_dir))

        proposals.extend(self.scan_failing_tests())
        proposals.extend(self.scan_postmortem_suggestions())
        return proposals

    def scan_todos(self, repo_dir: Path) -> list:
        """Find TODO/FIXME comments in code."""
        proposals = []
        try:
            result = subprocess.run(
                ["grep", "-rn",
                 "--exclude-dir=node_modules", "--exclude-dir=.git",
                 "--exclude-dir=dist", "--exclude-dir=build", "--exclude-dir=vendor",
                 "--include=*.ts", "--include=*.tsx",
                 "--include=*.py", "--include=*.js", "--include=*.jsx",
                 "-E", r"(TODO|FIXME|HACK|XXX):", str(repo_dir)],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.strip().split("\n")[:20]:
                if not line.strip():
                    continue
                # Parse: file:line:content
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                filepath, lineno, content = parts[0], parts[1], parts[2].strip()
                key = f"todo:{filepath}:{lineno}"
                if key in self.discovered:
                    continue
                self.discovered.add(key)
                proposals.append({
                    "type": "todo",
                    "instruction": f"Resolve TODO at {filepath}:{lineno} — {content}",
                    "file": filepath,
                    "line": int(lineno),
                    "risk_level": "low",
                    "repo": str(repo_dir),
                })
        except (subprocess.TimeoutExpired, Exception):
            pass
        return proposals

    def scan_lint_errors(self, repo_dir: Path) -> list:
        """Check for lint errors."""
        proposals = []
        pkg_json = repo_dir / "package.json"
        if not pkg_json.exists():
            return proposals

        try:
            pkg = json.loads(pkg_json.read_text())
            if "lint" not in pkg.get("scripts", {}):
                return proposals

            result = subprocess.run(
                ["npm", "run", "lint", "--", "--format", "json"],
                cwd=str(repo_dir), capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0 and result.stdout:
                key = f"lint:{repo_dir.name}"
                if key not in self.discovered:
                    self.discovered.add(key)
                    error_count = result.stdout.count("error")
                    proposals.append({
                        "type": "lint",
                        "instruction": f"Fix lint errors in {repo_dir.name} ({error_count} issues found)",
                        "risk_level": "low",
                        "repo": str(repo_dir),
                        "output": result.stdout[:500],
                    })
        except (subprocess.TimeoutExpired, Exception):
            pass
        return proposals

    def scan_type_errors(self, repo_dir: Path) -> list:
        """Check for TypeScript type errors."""
        proposals = []
        tsconfig = repo_dir / "tsconfig.json"
        if not tsconfig.exists():
            return proposals

        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                cwd=str(repo_dir), capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                key = f"typecheck:{repo_dir.name}"
                if key not in self.discovered:
                    self.discovered.add(key)
                    error_lines = [l for l in result.stdout.split("\n") if "error TS" in l]
                    proposals.append({
                        "type": "typecheck",
                        "instruction": f"Fix type errors in {repo_dir.name} ({len(error_lines)} errors)",
                        "risk_level": "low",
                        "repo": str(repo_dir),
                        "output": result.stdout[:500],
                    })
        except (subprocess.TimeoutExpired, Exception):
            pass
        return proposals

    def scan_failing_tests(self) -> list:
        """Check sessions for recently failed tests."""
        proposals = []
        if not SESSIONS_DIR.exists():
            return proposals

        for session_dir in SESSIONS_DIR.iterdir():
            events_dir = session_dir / "events"
            if not events_dir.exists():
                continue
            events_file = events_dir / "events.jsonl"
            if not events_file.exists():
                continue

            # Look for recent test failures
            try:
                lines = events_file.read_text().strip().split("\n")
                for line in lines[-20:]:
                    event = json.loads(line)
                    if event.get("type") == "test_failure":
                        key = f"test:{session_dir.name}:{event.get('test', '')}"
                        if key not in self.discovered:
                            self.discovered.add(key)
                            proposals.append({
                                "type": "test_failure",
                                "instruction": f"Fix failing test: {event.get('test', 'unknown')}",
                                "session_id": session_dir.name,
                                "risk_level": "medium",
                                "output": event.get("output", "")[:300],
                            })
            except Exception:
                continue
        return proposals

    def scan_postmortem_suggestions(self) -> list:
        """Check for unapproved postmortem knowledge suggestions."""
        proposals = []
        knowledge_dir = Path("/opt/workstation/knowledge")
        proposed_dir = knowledge_dir / "proposed"
        if not proposed_dir.exists():
            return proposals

        for f in proposed_dir.glob("*.yaml"):
            key = f"postmortem:{f.stem}"
            if key not in self.discovered:
                self.discovered.add(key)
                proposals.append({
                    "type": "knowledge_proposal",
                    "instruction": f"Review and apply knowledge trigger: {f.stem}",
                    "file": str(f),
                    "risk_level": "low",
                })
        return proposals

    def create_task_from_proposal(self, proposal: dict) -> Optional[dict]:
        """Convert a discovered proposal into a queued task."""
        task_id = f"auto-{int(time.time())}-{proposal['type']}"
        task_meta = {
            "task_id": task_id,
            "type": proposal["type"],
            "instruction": proposal["instruction"],
            "risk_level": proposal.get("risk_level", "medium"),
            "source": "autonomyd",
            "status": "proposed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo": proposal.get("repo", ""),
            "session_id": proposal.get("session_id", ""),
        }

        task_dir = TASKS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "meta.json").write_text(json.dumps(task_meta, indent=2))
        return task_meta

    def run_once(self) -> list:
        """Run a single scan cycle. Returns list of proposed tasks."""
        proposals = self.scan_all()
        tasks = []
        for proposal in proposals:
            task = self.create_task_from_proposal(proposal)
            if task:
                tasks.append(task)
        return tasks

    def run_forever(self):
        """Main daemon loop."""
        print(f"[autonomyd] Starting. Scan interval: {SCAN_INTERVAL}s")
        while True:
            try:
                tasks = self.run_once()
                if tasks:
                    print(f"[autonomyd] Discovered {len(tasks)} new tasks")
                    for t in tasks:
                        print(f"  - [{t['risk_level']}] {t['instruction'][:80]}")
            except Exception as e:
                print(f"[autonomyd] Error: {e}")
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    daemon = AutonomyDaemon()
    daemon.run_forever()
