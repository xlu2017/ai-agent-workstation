#!/usr/bin/env python3
"""
knowledge-loader.py — Determine which knowledge files activate for a given task.

Loads knowledge YAML files from /opt/workstation/knowledge/ and determines
which ones are relevant based on:
  - Keywords in the task description
  - File paths being modified
  - Packages in the project

Usage:
    python3 knowledge-loader.py --task "Add a React component for user profile"
    python3 knowledge-loader.py --paths src/components/UserProfile.tsx
    python3 knowledge-loader.py --packages react next typescript
    python3 knowledge-loader.py --task "..." --paths "..." --packages "..."
"""

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


KNOWLEDGE_DIR = os.environ.get("KNOWLEDGE_DIR", "/opt/workstation/knowledge")


@dataclass
class KnowledgeItem:
    id: str
    description: str
    activation_keywords: list[str] = field(default_factory=list)
    activation_paths: list[str] = field(default_factory=list)
    activation_packages: list[str] = field(default_factory=list)
    content: str = ""
    source_file: str = ""
    score: float = 0.0


def load_knowledge_files(directory: str) -> list[KnowledgeItem]:
    """Load all YAML knowledge files from the directory."""
    items = []
    pattern = os.path.join(directory, "*.yaml")
    for filepath in sorted(glob.glob(pattern)):
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue
            item = KnowledgeItem(
                id=data.get("id", Path(filepath).stem),
                description=data.get("description", ""),
                activation_keywords=data.get("activation_keywords", []),
                activation_paths=data.get("activation_paths", []),
                activation_packages=data.get("activation_packages", []),
                content=data.get("content", ""),
                source_file=filepath,
            )
            items.append(item)
        except Exception as e:
            print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
    return items


def score_item(
    item: KnowledgeItem,
    task_words: set[str],
    paths: list[str],
    packages: set[str],
) -> float:
    """Score a knowledge item based on activation criteria."""
    score = 0.0

    # Keyword matching (case-insensitive)
    for keyword in item.activation_keywords:
        if keyword.lower() in task_words:
            score += 2.0

    # Path matching (glob patterns)
    for path in paths:
        for pattern in item.activation_paths:
            if fnmatch(path, pattern) or fnmatch(os.path.basename(path), pattern):
                score += 3.0
                break

    # Package matching
    for pkg in item.activation_packages:
        if pkg.lower() in packages:
            score += 2.5

    return score


def activate_knowledge(
    task: str = "",
    paths: list[str] | None = None,
    packages: list[str] | None = None,
    threshold: float = 2.0,
) -> list[KnowledgeItem]:
    """Determine which knowledge items activate for the given context."""
    items = load_knowledge_files(KNOWLEDGE_DIR)
    if not items:
        return []

    task_words = set(task.lower().split()) if task else set()
    file_paths = paths or []
    pkg_set = {p.lower() for p in (packages or [])}

    results = []
    for item in items:
        item.score = score_item(item, task_words, file_paths, pkg_set)
        if item.score >= threshold:
            results.append(item)

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Determine which knowledge files activate for a task"
    )
    parser.add_argument("--task", "-t", default="", help="Task description")
    parser.add_argument("--paths", "-p", nargs="*", default=[], help="File paths")
    parser.add_argument("--packages", nargs="*", default=[], help="Package names")
    parser.add_argument(
        "--threshold", type=float, default=2.0, help="Minimum activation score"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--content", action="store_true", help="Include full content")
    args = parser.parse_args()

    results = activate_knowledge(
        task=args.task,
        paths=args.paths,
        packages=args.packages,
        threshold=args.threshold,
    )

    if args.json:
        output = []
        for item in results:
            entry = {
                "id": item.id,
                "description": item.description,
                "score": item.score,
                "source": item.source_file,
            }
            if args.content:
                entry["content"] = item.content
            output.append(entry)
        print(json.dumps(output, indent=2))
    else:
        if not results:
            print("No knowledge items activated.")
            return
        print(f"Activated {len(results)} knowledge item(s):\n")
        for item in results:
            print(f"  [{item.score:.1f}] {item.id} — {item.description}")
            if args.content:
                print(f"\n{item.content}\n{'─' * 60}\n")


if __name__ == "__main__":
    main()
