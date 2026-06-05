#!/usr/bin/env bash
# start-hatchet-worker.sh — start the platform Hatchet worker on the host
set -euo pipefail

WORKSTATION_DIR="${WORKSTATION_DIR:-$HOME/ai-workstation}"
VENV_DIR="${CONTROL_PLANE_VENV:-$WORKSTATION_DIR/.venv-control-plane}"

cd "$WORKSTATION_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
. "$VENV_DIR/bin/activate"

pip install -q -r requirements-control-plane.txt

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  . .env
  set +a
fi

export PYTHONPATH="$WORKSTATION_DIR/control-plane${PYTHONPATH:+:$PYTHONPATH}"
exec python control-plane/platform_queue/worker.py
