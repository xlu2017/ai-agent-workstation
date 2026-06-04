"""
Fork-and-Prove Mode — multi-candidate parallel execution for ambiguous tasks.

When a task is ambiguous, instead of asking clarification questions,
the system generates multiple plausible interpretations, scores them,
and implements qualifying candidates in isolated sessions/branches.
"""

import json
import os
import string
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from executors.base import ExecutorAdapter, TaskPacket, TaskResult, SESSIONS_DIR
from executors.direct_executor import DirectExecutor

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get(
    "LITELLM_MASTER_KEY",
    "<litellm-key>",
)
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")

POLICIES_DIR = Path(__file__).parent.parent / "policies"


def load_policy() -> dict:
    import yaml
    policy_path = POLICIES_DIR / "fork-and-prove.yaml"
    if policy_path.exists():
        with open(policy_path) as f:
            return yaml.safe_load(f)
    return {
        "candidate_threshold": 0.72,
        "near_tie_delta": 0.08,
        "max_candidates": 3,
        "max_parallel_sessions": 3,
        "max_runtime_minutes_per_candidate": 90,
        "max_total_token_cost_usd": 15,
        "allowed_risk_level": "medium",
        "final_status": "needs_review",
        "blocked_operations": ["push_to_main", "auto_merge", "modify_secrets"],
    }


def load_autonomy_policy() -> dict:
    import yaml
    policy_path = POLICIES_DIR / "full-autonomy-branch.yaml"
    if policy_path.exists():
        with open(policy_path) as f:
            return yaml.safe_load(f)
    return {}


class CandidateScorer:
    """Score candidate interpretations on 7 dimensions."""

    DIMENSIONS = [
        "user_intent_fit",
        "expected_value",
        "implementability",
        "validation_confidence",
        "risk_penalty",
        "cost_penalty",
        "scope_bloat_penalty",
    ]

    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL

    def generate_candidates(self, instruction: str, context: dict, max_candidates: int = 5) -> list:
        """Use LLM to generate candidate interpretations for an ambiguous task."""
        import urllib.request

        prompt = f"""You are analyzing an ambiguous coding task. Generate {max_candidates} distinct plausible interpretations.

Task instruction: {instruction}

Context:
- Repository: {context.get('repo', 'unknown')}
- Branch: {context.get('branch', 'unknown')}
- Recent files: {json.dumps(context.get('recent_files', [])[:10])}
- UI context: {context.get('ui_context', 'none')[:500]}
- Editor context: {context.get('editor_context', 'none')[:500]}

For each interpretation, provide:
1. A short title (slug-friendly)
2. A detailed interpretation of what the user likely means
3. Planned file changes
4. How to validate success
5. Risk level (low/medium/high)

Return ONLY valid JSON array with this schema per item:
{{
  "title": "short-slug-title",
  "interpretation": "detailed interpretation",
  "planned_changes": ["file1.ts: add X", "file2.ts: modify Y"],
  "validation_plan": ["npm test", "npm run build"],
  "risk_level": "low"
}}

Return {max_candidates} candidates. No markdown, no explanation, just the JSON array."""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 3000,
        }

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{LITELLM_URL}/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LITELLM_KEY}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        try:
            candidates = json.loads(content)
            if not isinstance(candidates, list):
                candidates = [candidates]
            return candidates[:max_candidates]
        except json.JSONDecodeError:
            return []

    def score_candidates(self, candidates: list, instruction: str, context: dict) -> list:
        """Score each candidate on all dimensions. Returns candidates with scores."""
        import urllib.request

        scored = []
        for candidate in candidates:
            score_prompt = f"""Score this candidate interpretation for the given task.

Original task: {instruction}
Candidate title: {candidate.get('title', '')}
Candidate interpretation: {candidate.get('interpretation', '')}
Planned changes: {json.dumps(candidate.get('planned_changes', []))}
Validation plan: {json.dumps(candidate.get('validation_plan', []))}
Risk level: {candidate.get('risk_level', 'medium')}

Score each dimension from 0.0 to 1.0:
- user_intent_fit: How well does this match what the user likely wants?
- expected_value: How valuable is this interpretation if correct?
- implementability: How feasible is this to implement correctly?
- validation_confidence: How confident can we be that validation will catch errors?
- risk_penalty: How risky is this? (0.0 = very risky, 1.0 = safe)
- cost_penalty: How expensive? (0.0 = very expensive, 1.0 = cheap)
- scope_bloat_penalty: How much scope creep? (0.0 = massive bloat, 1.0 = minimal)

Return ONLY valid JSON:
{{"user_intent_fit": 0.0, "expected_value": 0.0, "implementability": 0.0, "validation_confidence": 0.0, "risk_penalty": 0.0, "cost_penalty": 0.0, "scope_bloat_penalty": 0.0}}"""

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": score_prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            }

            try:
                data = json.dumps(payload).encode()
                req = urllib.request.Request(
                    f"{LITELLM_URL}/v1/chat/completions",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {LITELLM_KEY}",
                    },
                )
                resp = urllib.request.urlopen(req, timeout=30)
                result = json.loads(resp.read())
                score_content = result["choices"][0]["message"]["content"].strip()

                if score_content.startswith("```"):
                    score_content = score_content.split("\n", 1)[1]
                    if score_content.endswith("```"):
                        score_content = score_content[:-3]
                    score_content = score_content.strip()

                score_breakdown = json.loads(score_content)
            except Exception:
                score_breakdown = {dim: 0.5 for dim in self.DIMENSIONS}

            weights = {
                "user_intent_fit": 0.25,
                "expected_value": 0.20,
                "implementability": 0.20,
                "validation_confidence": 0.15,
                "risk_penalty": 0.10,
                "cost_penalty": 0.05,
                "scope_bloat_penalty": 0.05,
            }

            total_score = sum(
                score_breakdown.get(dim, 0.5) * weights.get(dim, 0.1)
                for dim in self.DIMENSIONS
            )

            letter = string.ascii_lowercase[len(scored)] if len(scored) < 26 else str(len(scored))

            scored_candidate = {
                "candidate_id": f"candidate-{letter}",
                "title": candidate.get("title", f"interpretation-{letter}"),
                "interpretation": candidate.get("interpretation", ""),
                "planned_changes": candidate.get("planned_changes", []),
                "validation_plan": candidate.get("validation_plan", []),
                "risk_level": candidate.get("risk_level", "medium"),
                "score": round(total_score, 4),
                "score_breakdown": {k: round(v, 4) for k, v in score_breakdown.items() if k in self.DIMENSIONS},
                "selected_for_implementation": False,
            }
            scored.append(scored_candidate)

        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored


class ForkAndProveOrchestrator:
    """Orchestrates multi-candidate fork execution."""

    def __init__(self, parent_session_id: str, policy: dict = None):
        self.parent_session_id = parent_session_id
        self.policy = policy or load_policy()
        self.session_dir = SESSIONS_DIR / parent_session_id
        self.fork_dir = self.session_dir / "fork-and-prove"
        self.fork_dir.mkdir(parents=True, exist_ok=True)
        self.scorer = CandidateScorer()
        self.executor = DirectExecutor()

    def run(self, instruction: str, worktree: str, branch: str, context: dict = None) -> dict:
        """Full fork-and-prove execution flow."""
        context = context or {}
        start_time = time.time()

        context["repo"] = worktree
        context["branch"] = branch

        max_candidates = self.policy.get("max_candidates", 3)
        threshold = self.policy.get("candidate_threshold", 0.72)
        near_tie_delta = self.policy.get("near_tie_delta", 0.08)

        candidates = self.scorer.generate_candidates(instruction, context, max_candidates + 2)
        if not candidates:
            return {"status": "failed", "error": "Could not generate candidate interpretations"}

        scored_candidates = self.scorer.score_candidates(candidates, instruction, context)

        selected = self._select_candidates(scored_candidates, threshold, near_tie_delta, max_candidates)

        self._save_candidates(scored_candidates)

        results = []
        for candidate in selected:
            result = self._execute_candidate(candidate, worktree, branch, instruction, context)
            results.append(result)

        comparison = self._generate_comparison_report(instruction, scored_candidates, results, time.time() - start_time)
        self._save_comparison_report(comparison)

        return {
            "status": "completed",
            "candidates_generated": len(scored_candidates),
            "candidates_implemented": len(selected),
            "results": results,
            "comparison_report": str(self.fork_dir / "comparison.md"),
            "duration_seconds": time.time() - start_time,
        }

    def _select_candidates(self, scored: list, threshold: float, near_tie_delta: float, max_candidates: int) -> list:
        """Select candidates for implementation based on threshold and near-tie rules."""
        if not scored:
            return []

        top_score = scored[0]["score"]
        selected = []

        for candidate in scored[:max_candidates]:
            if candidate["score"] >= threshold:
                candidate["selected_for_implementation"] = True
                selected.append(candidate)
            elif candidate["score"] >= top_score - near_tie_delta:
                candidate["selected_for_implementation"] = True
                selected.append(candidate)

        if not selected and scored:
            scored[0]["selected_for_implementation"] = True
            selected.append(scored[0])

        return selected

    def _execute_candidate(self, candidate: dict, parent_worktree: str, parent_branch: str, instruction: str, context: dict) -> dict:
        """Execute a single candidate in an isolated session."""
        candidate_id = candidate["candidate_id"]
        slug = candidate["title"].replace(" ", "-").lower()[:30]
        letter = candidate_id.split("-")[-1]

        child_session_id = f"{self.parent_session_id}-{candidate_id}"
        child_branch = f"{parent_branch}/candidate-{letter}-{slug}"

        child_session_dir = SESSIONS_DIR / child_session_id
        child_session_dir.mkdir(parents=True, exist_ok=True)
        (child_session_dir / "events").mkdir(exist_ok=True)

        worktree_path = str(child_session_dir / "worktree")

        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", child_branch, worktree_path],
                cwd=parent_worktree, capture_output=True, text=True, timeout=30,
            )
        except Exception as error:
            try:
                subprocess.run(
                    ["git", "worktree", "add", worktree_path, "-b", child_branch, "HEAD"],
                    cwd=parent_worktree, capture_output=True, text=True, timeout=30,
                )
            except Exception:
                return {
                    "candidate_id": candidate_id,
                    "status": "failed",
                    "error": f"Could not create worktree: {error}",
                    "branch": child_branch,
                }

        candidate_instruction = f"""## Task Interpretation
{candidate['interpretation']}

## Original Instruction
{instruction}

## Planned Changes
{chr(10).join('- ' + change for change in candidate.get('planned_changes', []))}

## Validation Plan
{chr(10).join('- ' + step for step in candidate.get('validation_plan', []))}

Complete this task. Follow the interpretation exactly. Run validation when done."""

        packet = TaskPacket(
            task_id=f"fork-{candidate_id}-{uuid.uuid4().hex[:8]}",
            session_id=child_session_id,
            instruction=candidate_instruction,
            worktree_path=worktree_path,
            branch=child_branch,
            ui_context=context.get("ui_context", ""),
            editor_context=context.get("editor_context", ""),
            terminal_context=context.get("terminal_context", ""),
            activated_knowledge=context.get("activated_knowledge", []),
        )

        start = time.time()
        task_result = self.executor.run_task(child_session_id, packet)
        duration = time.time() - start

        status = "needs_review"
        if task_result.status == "committed":
            status = "passed"
        elif task_result.status == "failed":
            status = "failed"

        return {
            "candidate_id": candidate_id,
            "title": candidate["title"],
            "score": candidate["score"],
            "status": status,
            "branch": child_branch,
            "worktree": worktree_path,
            "session_id": child_session_id,
            "files_edited": task_result.files_edited,
            "commit_sha": task_result.commit_sha,
            "duration_seconds": round(duration, 1),
            "tests_passed": task_result.tests_passed,
            "tests_failed": task_result.tests_failed,
        }

    def _save_candidates(self, candidates: list):
        """Save candidate plans to JSON file."""
        candidates_path = self.fork_dir / "candidates.json"
        with open(candidates_path, "w") as f:
            json.dump(candidates, f, indent=2)

    def _save_comparison_report(self, report: str):
        """Save comparison report as markdown."""
        report_path = self.fork_dir / "comparison.md"
        with open(report_path, "w") as f:
            f.write(report)

    def _generate_comparison_report(self, instruction: str, candidates: list, results: list, total_duration: float) -> str:
        """Generate markdown comparison report."""
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Fork-and-Prove Comparison Report",
            f"\nGenerated: {now}",
            f"\n## Task Instruction\n\n{instruction}",
            f"\n## Candidates Considered ({len(candidates)})\n",
        ]

        for candidate in candidates:
            selected = "IMPLEMENTED" if candidate.get("selected_for_implementation") else "skipped"
            lines.append(f"### {candidate['candidate_id']}: {candidate['title']} [{selected}]")
            lines.append(f"- Score: {candidate['score']:.4f}")
            lines.append(f"- Risk: {candidate['risk_level']}")
            lines.append(f"- Interpretation: {candidate['interpretation'][:200]}")
            breakdown = candidate.get("score_breakdown", {})
            if breakdown:
                lines.append("- Score breakdown:")
                for dim, val in breakdown.items():
                    lines.append(f"  - {dim}: {val:.3f}")
            lines.append("")

        lines.append(f"\n## Implementation Results ({len(results)})\n")

        for result in results:
            lines.append(f"### {result['candidate_id']}: {result.get('title', '')}")
            lines.append(f"- Status: **{result['status']}**")
            lines.append(f"- Branch: `{result['branch']}`")
            lines.append(f"- Files changed: {result.get('files_edited', [])}")
            lines.append(f"- Commit: `{result.get('commit_sha', 'none')}`")
            lines.append(f"- Tests: {result.get('tests_passed', 0)} passed, {result.get('tests_failed', 0)} failed")
            lines.append(f"- Duration: {result.get('duration_seconds', 0):.1f}s")
            lines.append(f"- Score: {result.get('score', 0):.4f}")
            lines.append("")

        passed_results = [r for r in results if r["status"] == "passed"]
        if passed_results:
            best = max(passed_results, key=lambda r: r.get("score", 0))
            lines.append(f"\n## Recommended Candidate\n")
            lines.append(f"**{best['candidate_id']}** ({best.get('title', '')})")
            lines.append(f"- Score: {best.get('score', 0):.4f}")
            lines.append(f"- Branch: `{best['branch']}`")
        else:
            lines.append("\n## Recommended Candidate\n")
            lines.append("No candidates passed validation. Manual review required.")

        lines.append(f"\n## Merge Strategy\n")
        if len(passed_results) > 1:
            lines.append("Multiple candidates passed. Options:")
            lines.append("1. Merge the recommended candidate only")
            lines.append("2. Cherry-pick specific changes from multiple candidates")
            lines.append("3. Manual combination of approaches")
            lines.append("\n### Potential Conflicts")
            all_files = set()
            conflict_files = set()
            for result in passed_results:
                for f in result.get("files_edited", []):
                    if f in all_files:
                        conflict_files.add(f)
                    all_files.add(f)
            if conflict_files:
                lines.append(f"Files modified by multiple candidates: {sorted(conflict_files)}")
            else:
                lines.append("No file conflicts detected — candidates may be combinable.")
        elif len(passed_results) == 1:
            lines.append("Single candidate passed. Direct merge recommended.")
        else:
            lines.append("No candidates passed. Manual intervention required.")

        lines.append(f"\n## Summary\n")
        lines.append(f"- Total candidates generated: {len(candidates)}")
        lines.append(f"- Candidates implemented: {len(results)}")
        lines.append(f"- Candidates passed: {len(passed_results)}")
        lines.append(f"- Total duration: {total_duration:.1f}s")
        lines.append(f"- Final status: needs_review (auto-merge disabled)")

        return "\n".join(lines)
