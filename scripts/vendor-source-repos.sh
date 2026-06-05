#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/config/vendor-repos.json"
LOCK="$ROOT/config/vendor-repos.lock.json"

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: missing $MANIFEST" >&2
  exit 1
fi

python3 - <<'PY' "$ROOT" "$MANIFEST" "$LOCK"
import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
lock_path = Path(sys.argv[3])
manifest = json.loads(manifest_path.read_text())
locks = {"repos": []}

for repo in manifest["repos"]:
    name = repo["name"]
    upstream = repo["upstream"]
    ref = repo["ref"]
    path = root / repo["path"]
    tmp = root / ".vendor-tmp" / name

    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning {name} from {upstream} at {ref}")
    subprocess.run(["git", "clone", upstream, str(tmp)], check=True)
    subprocess.run(["git", "fetch", "--tags", "origin"], cwd=tmp, check=True)
    subprocess.run(["git", "checkout", ref], cwd=tmp, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp, text=True).strip()

    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tmp, path, ignore=shutil.ignore_patterns(".git"))

    locks["repos"].append({
        "name": name,
        "upstream": upstream,
        "ref": ref,
        "commit_sha": sha,
        "path": repo["path"],
        "required_for": repo.get("required_for", ""),
    })

if (root / ".vendor-tmp").exists():
    shutil.rmtree(root / ".vendor-tmp")

lock_path.write_text(json.dumps(locks, indent=2) + "\n")
print(f"Wrote {lock_path}")
print("Next: git add vendor config/vendor-repos.lock.json && git commit")
PY
