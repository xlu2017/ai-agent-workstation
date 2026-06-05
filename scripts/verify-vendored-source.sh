#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/config/vendor-repos.json"
LOCK="$ROOT/config/vendor-repos.lock.json"

if [[ ! -f "$MANIFEST" ]]; then
  echo "FAIL: missing config/vendor-repos.json" >&2
  exit 1
fi
if [[ ! -f "$LOCK" ]]; then
  echo "FAIL: missing config/vendor-repos.lock.json. Run scripts/vendor-source-repos.sh and commit it." >&2
  exit 1
fi

python3 - <<'PY' "$ROOT" "$MANIFEST" "$LOCK"
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads(Path(sys.argv[2]).read_text())
lock = json.loads(Path(sys.argv[3]).read_text())
locked = {entry["name"]: entry for entry in lock.get("repos", [])}
failed = False

for repo in manifest["repos"]:
    name = repo["name"]
    path = root / repo["path"]
    entry = locked.get(name)
    if entry is None:
        print(f"FAIL: {name} missing from vendor lock")
        failed = True
        continue
    if not path.exists():
        print(f"FAIL: {name} source tree missing at {repo['path']}")
        failed = True
        continue
    if not any(path.iterdir()):
        print(f"FAIL: {name} source tree is empty at {repo['path']}")
        failed = True
        continue
    if (path / ".git").exists():
        print(f"FAIL: {name} contains nested .git directory. Vendor full source, not a nested repo.")
        failed = True
        continue
    print(f"OK: {name} vendored at {repo['path']} ({entry.get('commit_sha')})")

if failed:
    raise SystemExit(1)
PY
