#!/usr/bin/env bash
# list-worktrees.sh — List all active agent worktrees with their resources
set -euo pipefail

WORKSTATION_DIR="/opt/workstation"
REPOS_DIR="$WORKSTATION_DIR/repos"
PORT_FILE="$WORKSTATION_DIR/.port-allocations"

echo "=== Active Worktrees ==="
echo ""

found=0
for meta in "$REPOS_DIR"/*/.worktree-meta.json; do
    [[ -f "$meta" ]] || continue
    found=1

    name=$(jq -r '.repo + "-" + (.branch | gsub("/"; "-"))' "$meta" 2>/dev/null || basename "$(dirname "$meta")")
    branch=$(jq -r .branch "$meta" 2>/dev/null || echo "unknown")
    port=$(jq -r .allocated_port "$meta" 2>/dev/null || echo "none")
    session=$(jq -r .tmux_session "$meta" 2>/dev/null || echo "none")
    created=$(jq -r .created_at "$meta" 2>/dev/null || echo "unknown")
    path=$(dirname "$meta")

    # Check tmux session status
    if tmux has-session -t "$session" 2>/dev/null; then
        status="ACTIVE"
    else
        status="NO SESSION"
    fi

    printf "%-30s %-20s port:%-5s %s\n" "$name" "[$status]" "$port" "$branch"
    printf "  Path: %s\n" "$path"
    printf "  Created: %s\n\n" "$created"
done

if [[ $found -eq 0 ]]; then
    echo "No active worktrees found."
    echo ""
    echo "Create one with: create-worktree.sh <repo-name> <branch-name>"
fi

# Show port allocations
if [[ -f "$PORT_FILE" && -s "$PORT_FILE" ]]; then
    echo ""
    echo "=== Port Allocations ==="
    cat "$PORT_FILE"
fi
