#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/vendor/openhands"
REPO="${OPENHANDS_UPSTREAM_REPO:-https://github.com/OpenHands/OpenHands.git}"
REF="${OPENHANDS_REF:-main}"
LOCK="$ROOT/config/openhands.lock.json"

mkdir -p "$ROOT/vendor" "$ROOT/config"

if [[ ! -d "$SRC/.git" ]]; then
  git clone "$REPO" "$SRC"
fi

cd "$SRC"
git fetch --tags origin
git checkout "$REF"
SHA="$(git rev-parse HEAD)"
TAG="${SHA:0:12}"

cat > "$LOCK" <<EOF
{
  "name": "openhands-runtime",
  "upstream_repository": "$REPO",
  "source_dir": "vendor/openhands",
  "ref": "$REF",
  "commit_sha": "$SHA",
  "image_name": "localhost/openhands-platform",
  "image_tag": "$TAG",
  "private_registry_image": null
}
EOF

echo "OpenHands vendored at $SHA"
echo "Lock file: $LOCK"
