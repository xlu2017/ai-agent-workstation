#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT/scripts/verify-vendored-source.sh"

missing=0
for image in localhost/openhands-platform:local localhost/litellm-platform:local; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "OK: image exists: $image"
  else
    echo "FAIL: image missing: $image"
    missing=1
  fi
done

if grep -R "ghcr.io/all-hands-ai/openhands:latest\|ghcr.io/berriai/litellm:main-latest" "$ROOT" \
  --exclude-dir=.git --exclude-dir=vendor >/dev/null 2>&1; then
  echo "FAIL: floating public runtime image reference remains outside vendor/"
  missing=1
fi

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

echo "OK: offline runtime readiness checks passed"
