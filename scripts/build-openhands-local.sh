#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/vendor/openhands"
LOCK="$ROOT/config/openhands.lock.json"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: vendor/openhands is missing. Run scripts/vendor-openhands.sh first." >&2
  exit 1
fi
if [[ ! -f "$LOCK" ]]; then
  echo "ERROR: config/openhands.lock.json is missing. Run scripts/vendor-openhands.sh first." >&2
  exit 1
fi

IMAGE_NAME="$(python3 -c 'import json;print(json.load(open("config/openhands.lock.json"))["image_name"])')"
IMAGE_TAG="$(python3 -c 'import json;print(json.load(open("config/openhands.lock.json"))["image_tag"] or "local")')"
IMAGE="$IMAGE_NAME:$IMAGE_TAG"
LATEST="$IMAGE_NAME:local"

cd "$SRC"
docker build -t "$IMAGE" -t "$LATEST" .

echo "Built $IMAGE"
echo "Tagged $LATEST"
