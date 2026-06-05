#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENHANDS_SRC="$ROOT/vendor/openhands"
LITELLM_SRC="$ROOT/vendor/litellm"

if [[ ! -d "$OPENHANDS_SRC" ]]; then
  echo "ERROR: vendor/openhands is missing. Run scripts/vendor-source-repos.sh first." >&2
  exit 1
fi
if [[ ! -d "$LITELLM_SRC" ]]; then
  echo "ERROR: vendor/litellm is missing. Run scripts/vendor-source-repos.sh first." >&2
  exit 1
fi

cd "$OPENHANDS_SRC"
docker build -t localhost/openhands-platform:local .

cd "$LITELLM_SRC"
docker build -t localhost/litellm-platform:local .

echo "Built localhost/openhands-platform:local"
echo "Built localhost/litellm-platform:local"
