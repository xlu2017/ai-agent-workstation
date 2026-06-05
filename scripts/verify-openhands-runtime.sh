#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/config/openhands.lock.json"
SRC="$ROOT/vendor/openhands"

if [[ ! -f "$LOCK" ]]; then
  echo "FAIL: config/openhands.lock.json is missing" >&2
  exit 1
fi
if [[ ! -d "$SRC/.git" ]]; then
  echo "FAIL: vendor/openhands is missing or is not a git checkout" >&2
  exit 1
fi

LOCK_SHA="$(python3 -c 'import json;print(json.load(open("config/openhands.lock.json"))["commit_sha"] or "")')"
IMAGE_NAME="$(python3 -c 'import json;print(json.load(open("config/openhands.lock.json"))["image_name"])')"
IMAGE_TAG="$(python3 -c 'import json;print(json.load(open("config/openhands.lock.json"))["image_tag"] or "local")')"
IMAGE="$IMAGE_NAME:$IMAGE_TAG"

cd "$SRC"
SRC_SHA="$(git rev-parse HEAD)"

if [[ -z "$LOCK_SHA" ]]; then
  echo "FAIL: lock file does not contain commit_sha. Run scripts/vendor-openhands.sh" >&2
  exit 1
fi
if [[ "$SRC_SHA" != "$LOCK_SHA" ]]; then
  echo "FAIL: vendor checkout does not match lock"
  echo "  lock:   $LOCK_SHA"
  echo "  vendor: $SRC_SHA"
  exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "FAIL: Docker image missing: $IMAGE"
  echo "Run scripts/build-openhands-local.sh"
  exit 1
fi

RUNNING_IMAGE="$(docker inspect openhands --format '{{.Config.Image}}' 2>/dev/null || true)"
if [[ -z "$RUNNING_IMAGE" ]]; then
  echo "WARN: OpenHands container is not running"
else
  echo "OpenHands container image: $RUNNING_IMAGE"
fi

echo "OK: OpenHands vendor checkout matches lock: $LOCK_SHA"
echo "OK: Local image exists: $IMAGE"
