#!/usr/bin/env bash
# create-worktree.sh — Create a new agent worktree with dedicated resources
set -euo pipefail

WORKSTATION_DIR="/opt/workstation"
REPOS_DIR="$WORKSTATION_DIR/repos"
LOGS_DIR="$WORKSTATION_DIR/logs"

usage() {
    echo "Usage: $0 <repo-name> <branch-name> [base-branch]"
    echo ""
    echo "Creates a new git worktree with:"
    echo "  - Dedicated branch"
    echo "  - Dedicated tmux session"
    echo "  - Dedicated browser profile"
    echo "  - Dedicated port allocation"
    echo ""
    echo "Example: $0 my-app feature/new-api main"
    exit 1
}

[[ $# -lt 2 ]] && usage

REPO_NAME="$1"
BRANCH_NAME="$2"
BASE_BRANCH="${3:-main}"

BARE_REPO="$REPOS_DIR/${REPO_NAME}.git"
WORKTREE_NAME="${REPO_NAME}-$(echo "$BRANCH_NAME" | tr '/' '-')"
WORKTREE_PATH="$REPOS_DIR/$WORKTREE_NAME"
PROFILE_DIR="$WORKSTATION_DIR/profiles/$WORKTREE_NAME"
SESSION_NAME="agent-$WORKTREE_NAME"

# Validate bare repo exists
if [[ ! -d "$BARE_REPO" ]]; then
    echo "Error: Bare repo not found at $BARE_REPO"
    echo "First clone: git clone --bare <url> $BARE_REPO"
    exit 1
fi

# Allocate port (base 5000, increment by worktree count)
PORT_FILE="$WORKSTATION_DIR/.port-allocations"
touch "$PORT_FILE"
EXISTING_COUNT=$(wc -l < "$PORT_FILE")
ALLOCATED_PORT=$((5000 + EXISTING_COUNT * 10))
echo "$WORKTREE_NAME:$ALLOCATED_PORT" >> "$PORT_FILE"

# Create worktree
echo "Creating worktree: $WORKTREE_PATH (branch: $BRANCH_NAME from $BASE_BRANCH)"
git -C "$BARE_REPO" worktree add "$WORKTREE_PATH" -b "$BRANCH_NAME" "$BASE_BRANCH" 2>/dev/null || \
    git -C "$BARE_REPO" worktree add "$WORKTREE_PATH" "$BRANCH_NAME"

# Create browser profile directory
mkdir -p "$PROFILE_DIR"

# Create tmux session
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "tmux session '$SESSION_NAME' already exists"
else
    tmux new-session -d -s "$SESSION_NAME" -c "$WORKTREE_PATH"
    tmux send-keys -t "$SESSION_NAME" "echo 'Worktree: $WORKTREE_PATH'" Enter
    tmux send-keys -t "$SESSION_NAME" "echo 'Port: $ALLOCATED_PORT'" Enter
    tmux send-keys -t "$SESSION_NAME" "echo 'Browser profile: $PROFILE_DIR'" Enter
fi

# Write metadata
cat > "$WORKTREE_PATH/.worktree-meta.json" <<EOF
{
    "repo": "$REPO_NAME",
    "branch": "$BRANCH_NAME",
    "base_branch": "$BASE_BRANCH",
    "worktree_path": "$WORKTREE_PATH",
    "tmux_session": "$SESSION_NAME",
    "browser_profile": "$PROFILE_DIR",
    "allocated_port": $ALLOCATED_PORT,
    "created_at": "$(date -Iseconds)"
}
EOF

echo ""
echo "=== Worktree Created ==="
echo "  Path:     $WORKTREE_PATH"
echo "  Branch:   $BRANCH_NAME"
echo "  Session:  $SESSION_NAME (tmux attach -t $SESSION_NAME)"
echo "  Port:     $ALLOCATED_PORT"
echo "  Profile:  $PROFILE_DIR"
echo ""
echo "To start Chrome with dedicated profile:"
echo "  google-chrome --user-data-dir=$PROFILE_DIR --remote-debugging-port=$((ALLOCATED_PORT + 1))"

log_entry="$(date -Iseconds) CREATE $WORKTREE_NAME branch=$BRANCH_NAME port=$ALLOCATED_PORT"
echo "$log_entry" >> "$LOGS_DIR/worktrees.log"
