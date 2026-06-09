"""
Duplicate commit guard — prevents two sessions from committing identical changes.

Before committing, computes the tree hash of the staged changes and checks
whether any branch in the repo already has a commit with that exact tree.
If so, the commit is rejected with details about which branch already has it.

Adapted from the OpenHands SDK pattern where EventLog.append() checks for
duplicate event IDs before persisting. Here we check tree hashes instead.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PROTECTED_BRANCHES = {"main", "master", "develop", "production"}


def check_duplicate_tree(worktree: str | Path) -> tuple[bool, str]:
    """Check if the current staged tree already exists as a commit in the repo.

    Returns (is_duplicate, detail_message).
    If is_duplicate is True, the commit should be rejected.
    """
    worktree = str(worktree)

    # Get the tree hash that would be committed
    try:
        result = subprocess.run(
            ["git", "write-tree"],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            # Nothing staged or git error — let the commit proceed normally
            return (False, "")
        pending_tree = result.stdout.strip()
    except Exception as e:
        logger.warning("commit_guard: write-tree failed: %s", e)
        return (False, "")

    if not pending_tree:
        return (False, "")

    # Check HEAD first — if the tree matches HEAD, there's nothing new to commit
    try:
        head_tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if head_tree.returncode == 0 and head_tree.stdout.strip() == pending_tree:
            return (True, "No changes to commit — working tree matches HEAD")
    except Exception:
        pass

    # Check all remote-tracking and local branches for a commit with this tree hash
    try:
        # Get all branch refs (local + remote)
        refs_result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/", "refs/remotes/"],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if refs_result.returncode != 0:
            return (False, "")

        for line in refs_result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            branch_name, commit_hash = parts[0], parts[1]

            # Get tree hash for this branch's HEAD
            tree_result = subprocess.run(
                ["git", "rev-parse", f"{commit_hash}^{{tree}}"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if tree_result.returncode == 0 and tree_result.stdout.strip() == pending_tree:
                return (
                    True,
                    f"Duplicate: branch '{branch_name}' already has a commit "
                    f"({commit_hash[:8]}) with identical tree {pending_tree[:8]}",
                )
    except Exception as e:
        logger.warning("commit_guard: branch scan failed: %s", e)

    return (False, "")
