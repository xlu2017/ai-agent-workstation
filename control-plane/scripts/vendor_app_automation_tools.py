#!/usr/bin/env python3
"""Clone or refresh app-automation vendor repositories.

This script intentionally vendors source trees into this repository so the
platform can patch connector runtimes directly. It does not automatically commit
large vendored trees; operators should review licenses and diffs first.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def ensure_vendor(tool: dict[str, Any], shallow: bool) -> None:
    repo_url = tool["repo_url"]
    target = ROOT / tool["target_dir"]
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        cmd = ["git", "clone"]
        if shallow:
            cmd += ["--depth", "1"]
        cmd += [repo_url, str(target)]
        run(cmd)
    else:
        if not (target / ".git").exists():
            raise SystemExit(f"Target exists but is not a git checkout: {target}")
        run(["git", "fetch", "--all", "--tags"], cwd=target)
        run(["git", "pull", "--ff-only"], cwd=target)

    patches = target / "VENDORED_PATCHES.md"
    if not patches.exists():
        patches.write_text(
            f"# Vendored patches: {tool['name']}\n\n"
            "Document all local changes to this vendored source tree here.\n\n"
            f"Upstream: {repo_url}\n"
            f"Role: {tool.get('role', '')}\n"
            f"License note: {tool.get('license', '')}\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="control-plane/vendor/app-automation/manifest.json")
    parser.add_argument("--tool", action="append", help="Vendor only a specific tool id. Can be repeated.")
    parser.add_argument("--full", action="store_true", help="Clone full history instead of --depth 1.")
    args = parser.parse_args()

    manifest = load_manifest(ROOT / args.manifest)
    selected = set(args.tool or [])
    for tool in manifest.get("selected_tools", []):
        if selected and tool.get("id") not in selected:
            continue
        ensure_vendor(tool, shallow=not args.full)


if __name__ == "__main__":
    main()
