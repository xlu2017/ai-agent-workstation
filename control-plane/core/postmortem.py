#!/usr/bin/env python3
"""
Postmortem Engine — Analyzes failed sessions and proposes knowledge triggers.

Flow:
1. Agent fails a task (test fails, build fails, wrong file edited, etc.)
2. Platform generates structured postmortem from timeline
3. Identifies what knowledge was missing
4. Proposes new knowledge trigger (YAML)
5. Human reviews and approves
6. Future sessions activate the knowledge automatically

Storage:
  /opt/workstation/sessions/<id>/postmortem.json
  /opt/workstation/sessions/<id>/postmortem.md
  /opt/workstation/knowledge/proposed/<id>.yaml (pending approval)
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge"))


class Postmortem:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = SESSIONS_DIR / session_id
        self.timeline_file = self.session_dir / "timeline.jsonl"

    def generate(self, failure_reason: str = "") -> dict:
        """Generate a structured postmortem from the session timeline."""
        events = self._load_events()
        meta = self._load_meta()

        # Analyze failure patterns
        errors = [e for e in events if e.get("type") == "error"]
        failed_tests = [e for e in events if e.get("type") == "test_result" and not e.get("passed")]
        failed_builds = [e for e in events if e.get("type") == "build_result" and not e.get("passed")]
        files_edited = [e for e in events if e.get("type") == "file_edited"]
        files_read = [e for e in events if e.get("type") == "file_read"]
        commands = [e for e in events if e.get("type") == "command_run"]

        # Identify wrong-file edits
        wrong_files = self._detect_wrong_file_edits(files_edited, meta)

        # Identify missing knowledge
        missing_knowledge = self._identify_missing_knowledge(errors, failed_tests, files_edited)

        # Build postmortem
        postmortem = {
            "session_id": self.session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task": meta.get("task", ""),
            "branch": meta.get("branch", ""),
            "outcome": "failed",
            "failure_reason": failure_reason or self._infer_failure_reason(errors, failed_tests, failed_builds),
            "analysis": {
                "total_events": len(events),
                "errors": len(errors),
                "failed_tests": len(failed_tests),
                "failed_builds": len(failed_builds),
                "files_read": len(files_read),
                "files_edited": len(files_edited),
                "commands_run": len(commands),
                "wrong_file_edits": wrong_files,
            },
            "root_causes": self._analyze_root_causes(errors, failed_tests, files_edited),
            "missing_knowledge": missing_knowledge,
            "proposed_triggers": self._propose_triggers(missing_knowledge, meta),
            "recommendations": self._build_recommendations(errors, failed_tests, wrong_files),
        }

        # Save
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "postmortem.json").write_text(json.dumps(postmortem, indent=2))
        (self.session_dir / "postmortem.md").write_text(self._to_markdown(postmortem))

        # Save proposed knowledge triggers
        for trigger in postmortem["proposed_triggers"]:
            self._save_proposed_trigger(trigger)

        return postmortem

    def _load_events(self) -> list:
        if not self.timeline_file.exists():
            return []
        events = []
        for line in self.timeline_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def _load_meta(self) -> dict:
        meta_file = self.session_dir / "session.json"
        if meta_file.exists():
            return json.loads(meta_file.read_text())
        return {}

    def _detect_wrong_file_edits(self, file_edits: list, meta: dict) -> list:
        worktree = meta.get("worktree_path", "")
        wrong = []
        for edit in file_edits:
            f = edit.get("file", "")
            if f and worktree and f.startswith("/") and not f.startswith(worktree):
                wrong.append({"file": f, "expected_worktree": worktree})
        return wrong

    def _infer_failure_reason(self, errors: list, failed_tests: list, failed_builds: list) -> str:
        if failed_builds:
            return f"Build failed: {failed_builds[-1].get('output', '')[:100]}"
        if failed_tests:
            return f"Test failed: {failed_tests[-1].get('test', '?')} — {failed_tests[-1].get('output', '')[:100]}"
        if errors:
            return f"Error: {errors[-1].get('error_type', '?')} — {errors[-1].get('message', '')[:100]}"
        return "Unknown failure"

    def _analyze_root_causes(self, errors: list, failed_tests: list, file_edits: list) -> list:
        causes = []
        error_patterns = {}
        for e in errors:
            etype = e.get("error_type", "unknown")
            error_patterns[etype] = error_patterns.get(etype, 0) + 1

        for etype, count in error_patterns.items():
            if count >= 2:
                causes.append(f"Repeated {etype} errors ({count} times) — suggests structural misunderstanding")

        if failed_tests and not file_edits:
            causes.append("Tests failed but no files were edited — agent may not have identified the correct fix location")

        for test in failed_tests:
            if "generated" in test.get("test", "").lower() or "generated" in test.get("output", "").lower():
                causes.append("Failure involves generated code — agent may have edited generated files instead of source")

        return causes or ["No clear root cause identified from timeline"]

    def _identify_missing_knowledge(self, errors: list, failed_tests: list, file_edits: list) -> list:
        missing = []

        # Check for generated file edits
        generated_patterns = ["generated", "auto-generated", ".gen.", "dist/", "build/", "__pycache__"]
        for edit in file_edits:
            f = edit.get("file", "").lower()
            for pattern in generated_patterns:
                if pattern in f:
                    missing.append({
                        "type": "do_not_edit",
                        "description": f"File '{edit.get('file', '')}' appears to be generated",
                        "evidence": f"Agent edited what looks like a generated file",
                    })
                    break

        # Check for repeated test failures suggesting unknown constraint
        test_names = [t.get("test", "") for t in failed_tests]
        if len(test_names) > len(set(test_names)):
            missing.append({
                "type": "test_constraint",
                "description": "Same test failed multiple times — may need specific setup or fixture",
                "evidence": f"Tests: {list(set(test_names))[:3]}",
            })

        # Check for import/module errors
        for e in errors:
            msg = e.get("message", "").lower()
            if "modulenotfounderror" in msg or "cannot find module" in msg:
                missing.append({
                    "type": "dependency",
                    "description": "Missing dependency — agent needed to install something first",
                    "evidence": e.get("message", "")[:100],
                })
            elif "permission" in msg:
                missing.append({
                    "type": "permission",
                    "description": "Permission issue — agent needed elevated access or different user",
                    "evidence": e.get("message", "")[:100],
                })

        return missing

    def _propose_triggers(self, missing_knowledge: list, meta: dict) -> list:
        triggers = []
        for mk in missing_knowledge:
            trigger_id = f"{self.session_id}-{mk['type']}-{len(triggers)}"
            trigger = {
                "id": trigger_id,
                "description": mk["description"],
                "content": self._generate_content(mk),
                "activation_paths": self._infer_paths(mk, meta),
                "activation_keywords": self._infer_keywords(mk),
                "confidence": "medium",
                "evidence": [f"session: {self.session_id}", mk.get("evidence", "")],
                "status": "proposed",
                "proposed_at": datetime.now(timezone.utc).isoformat(),
            }
            triggers.append(trigger)
        return triggers

    def _generate_content(self, mk: dict) -> str:
        if mk["type"] == "do_not_edit":
            return f"Do not edit this file directly. It is generated. Find the source template or schema and modify that instead."
        elif mk["type"] == "test_constraint":
            return f"This test requires specific setup. Check fixtures, env vars, and database state before running."
        elif mk["type"] == "dependency":
            return f"Install required dependencies first. Check package.json/requirements.txt/Cargo.toml for needed packages."
        elif mk["type"] == "permission":
            return f"This operation requires specific permissions. Check file ownership and service accounts."
        return mk["description"]

    def _infer_paths(self, mk: dict, meta: dict) -> list:
        if "file" in mk.get("evidence", ""):
            # Extract file path patterns
            return ["**/*"]
        return [f"{meta.get('repo_path', '')}/**"]

    def _infer_keywords(self, mk: dict) -> list:
        keywords = []
        if mk["type"] == "do_not_edit":
            keywords.extend(["generated", "auto-generated", "do not edit"])
        elif mk["type"] == "dependency":
            keywords.extend(["ModuleNotFoundError", "cannot find module", "import"])
        elif mk["type"] == "test_constraint":
            keywords.extend(["test", "fixture", "setup"])
        return keywords

    def _save_proposed_trigger(self, trigger: dict):
        proposed_dir = KNOWLEDGE_DIR / "proposed"
        proposed_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{trigger['id']}.yaml"
        try:
            import yaml
            with open(proposed_dir / filename, "w") as f:
                yaml.dump(trigger, f, default_flow_style=False)
        except ImportError:
            with open(proposed_dir / filename, "w") as f:
                json.dump(trigger, f, indent=2)

    def _build_recommendations(self, errors: list, failed_tests: list, wrong_files: list) -> list:
        recs = []
        if wrong_files:
            recs.append("Agent edited files in the wrong worktree. Verify worktree path before editing.")
        if failed_tests:
            recs.append("Run tests earlier in the workflow to catch issues before spending tokens on wrong approaches.")
        if len(errors) > 3:
            recs.append("Many errors suggest the agent was working without sufficient context. Add knowledge triggers for this repo.")
        return recs or ["No specific recommendations. Session may need more context about project structure."]

    def _to_markdown(self, pm: dict) -> str:
        lines = [
            f"# Postmortem: {pm['session_id']}",
            "",
            f"**Task:** {pm['task']}",
            f"**Branch:** {pm['branch']}",
            f"**Outcome:** {pm['outcome']}",
            f"**Generated:** {pm['generated_at']}",
            "",
            f"## Failure Reason",
            f"{pm['failure_reason']}",
            "",
            f"## Analysis",
            f"- Events: {pm['analysis']['total_events']}",
            f"- Errors: {pm['analysis']['errors']}",
            f"- Failed tests: {pm['analysis']['failed_tests']}",
            f"- Failed builds: {pm['analysis']['failed_builds']}",
            f"- Files read: {pm['analysis']['files_read']}",
            f"- Files edited: {pm['analysis']['files_edited']}",
            f"- Wrong-file edits: {len(pm['analysis']['wrong_file_edits'])}",
            "",
            "## Root Causes",
        ]
        for cause in pm["root_causes"]:
            lines.append(f"- {cause}")

        lines.extend(["", "## Missing Knowledge"])
        for mk in pm["missing_knowledge"]:
            lines.append(f"- **{mk['type']}:** {mk['description']}")

        lines.extend(["", "## Proposed Knowledge Triggers"])
        for trigger in pm["proposed_triggers"]:
            lines.append(f"- `{trigger['id']}`: {trigger['description']} (status: {trigger['status']})")

        lines.extend(["", "## Recommendations"])
        for rec in pm["recommendations"]:
            lines.append(f"- {rec}")

        return "\n".join(lines)


def approve_trigger(trigger_id: str) -> bool:
    """Move a proposed trigger to active knowledge."""
    proposed_dir = KNOWLEDGE_DIR / "proposed"
    for f in proposed_dir.glob(f"{trigger_id}*"):
        try:
            import yaml
            trigger = yaml.safe_load(f.read_text())
        except (ImportError, Exception):
            trigger = json.loads(f.read_text())

        trigger["status"] = "active"
        trigger["approved_at"] = datetime.now(timezone.utc).isoformat()

        # Save to active knowledge
        active_file = KNOWLEDGE_DIR / f"{trigger['id']}.yaml"
        try:
            import yaml
            active_file.write_text(yaml.dump(trigger, default_flow_style=False))
        except ImportError:
            active_file.write_text(json.dumps(trigger, indent=2))

        # Remove from proposed
        f.unlink()
        return True
    return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 postmortem.py generate <session_id> [failure_reason]")
        print("  python3 postmortem.py approve <trigger_id>")
        sys.exit(1)

    action = sys.argv[1]
    if action == "generate" and len(sys.argv) > 2:
        pm = Postmortem(sys.argv[2])
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        result = pm.generate(reason)
        print(json.dumps(result, indent=2))
    elif action == "approve" and len(sys.argv) > 2:
        if approve_trigger(sys.argv[2]):
            print(f"Trigger '{sys.argv[2]}' approved and moved to active knowledge.")
        else:
            print(f"Trigger '{sys.argv[2]}' not found in proposed.", file=sys.stderr)
    else:
        print("Invalid arguments", file=sys.stderr)
