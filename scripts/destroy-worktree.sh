#!/usr/bin/env bash
# destroy-worktree.sh — Remove a worktree and clean up all associated resources
set -euo pipefail

WORKSTATION_DIR="/opt/workstation"
REPOS_DIR="$WORKSTATION_DIR/repos"
LOGS_DIR="$WORKSTATION_DIR/logs"

usage() {
    echo "Usage: $0 <worktree-name>"
    echo ""
    echo "Removes the worktree and cleans up:"
    echo "  - Git worktree"
    echo "  - tmux session"
    echo "  - Browser profile"
    echo "  - Port allocation"
    echo ""
    echo "Use 'list-worktrees.sh' to see active worktrees."
    exit 1
}

[[ $# -lt 1 ]] && usage

WORKTREE_NAME="$1"
WORKTREE_PATH="$REPOS_DIR/$WORKTREE_NAME"
PROFILE_DIR="$WORKSTATION_DIR/profiles/$WORKTREE_NAME"
SESSION_NAME="agent-$WORKTREE_NAME"
PORT_FILE="$WORKSTATION_DIR/.port-allocations"

if [[ ! -d "$WORKTREE_PATH" ]]; then
    echo "Error: Worktree not found at $WORKTREE_PATH"
    exit 1
fi

# Read metadata
if [[ -f "$WORKTREE_PATH/.worktree-meta.json" ]]; then
    REPO_NAME=$(jq -r .repo "$WORKTREE_PATH/.worktree-meta.json")
    BARE_REPO="$REPOS_DIR/${REPO_NAME}.git"
fi

echo "Destroying worktree: $WORKTREE_NAME"

# Kill tmux session
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
    echo "  Killed tmux session: $SESSION_NAME"
fi

# Remove worktree
if [[ -n "${BARE_REPO:-}" && -d "$BARE_REPO" ]]; then
    git -C "$BARE_REPO" worktree remove "$WORKTREE_PATH" --force 2>/dev/null || rm -rf "$WORKTREE_PATH"
else
    rm -rf "$WORKTREE_PATH"
fi
echo "  Removed worktree: $WORKTREE_PATH"

# Remove browser profile
if [[ -d "$PROFILE_DIR" ]]; then
    rm -rf "$PROFILE_DIR"
    echo "  Removed browser profile: $PROFILE_DIR"
fi

# Remove port allocation
if [[ -f "$PORT_FILE" ]]; then
    sed -i "/^${WORKTREE_NAME}:/d" "$PORT_FILE"
    echo "  Freed port allocation"
fi

log_entry="$(date -Iseconds) DESTROY $WORKTREE_NAME"
echo "$log_entry" >> "$LOGS_DIR/worktrees.log"

echo ""
echo "Worktree '$WORKTREE_NAME' destroyed."
