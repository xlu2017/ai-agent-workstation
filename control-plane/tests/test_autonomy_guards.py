"""
Tests for Full Autonomy Branch Mode guards.

Test cases:
1. Agent can create/edit/delete files in worktree.
2. Agent can run tests and commit.
3. Agent cannot write outside worktree.
4. Agent cannot modify .env or secrets.
5. Agent cannot push to main.
6. Agent cannot run destructive DB commands.
7. Agent can spawn helper session on separate branch.
8. Timeline records all actions.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from executors.autonomy_guards import (
    AutonomyGuardChain,
    BranchGuard,
    PathGuard,
    SecretGuard,
    DestructiveCommandGuard,
    CloudCommandGuard,
    DatabaseCommandGuard,
)

WORKTREE = "/opt/workstation/sessions/test-session/worktree"


def test_1_agent_can_edit_files_in_worktree():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_file_write(f"{WORKTREE}/src/index.ts")
    assert result.allowed, f"Should allow write in worktree: {result.reason}"
    result = guards.validate_file_write(f"{WORKTREE}/package.json")
    assert result.allowed
    result = guards.validate_file_delete(f"{WORKTREE}/src/old-file.ts")
    assert result.allowed
    print("PASS: test_1 agent can edit files in worktree")


def test_2_agent_can_commit():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_git_commit("feature-branch")
    assert result.allowed
    result = guards.validate_command("git add . && git commit -m 'fix: update'")
    assert result.allowed
    print("PASS: test_2 agent can commit on session branch")


def test_3_cannot_write_outside_worktree():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_file_write("/etc/passwd")
    assert not result.allowed, "Should block writes to /etc"
    result = guards.validate_file_write("/opt/workstation/sessions/other-session/worktree/file.ts")
    assert not result.allowed, "Should block writes to other sessions"
    result = guards.validate_file_write("/root/.bashrc")
    assert not result.allowed
    print("PASS: test_3 cannot write outside worktree")


def test_4_cannot_modify_secrets():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_file_write(f"{WORKTREE}/.env")
    assert not result.allowed, "Should block .env writes"
    result = guards.validate_file_write(f"{WORKTREE}/credentials.json")
    assert not result.allowed
    result = guards.validate_file_write(f"{WORKTREE}/server.key")
    assert not result.allowed
    result = guards.validate_file_read(f"{WORKTREE}/.env.production")
    assert not result.allowed
    print("PASS: test_4 cannot modify secrets")


def test_5_cannot_push_to_main():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_git_push("main")
    assert not result.allowed
    result = guards.validate_git_push("master")
    assert not result.allowed
    result = guards.validate_git_push("develop")
    assert not result.allowed
    result = guards.validate_git_push("production")
    assert not result.allowed
    result = guards.validate_git_push("feature-branch")
    assert result.allowed, "Should allow push to feature branch"
    print("PASS: test_5 cannot push to main/master/develop/production")


def test_6_cannot_run_destructive_db_commands():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_command("DROP DATABASE production")
    assert not result.allowed
    result = guards.validate_command("TRUNCATE TABLE users")
    assert not result.allowed
    result = guards.validate_command("DELETE FROM sessions;")
    assert not result.allowed
    result = guards.validate_command("rm -rf /")
    assert not result.allowed
    result = guards.validate_command("terraform destroy")
    assert not result.allowed
    result = guards.validate_command("aws ec2 create-instance")
    assert not result.allowed
    result = guards.validate_command("npm test")
    assert result.allowed, "Should allow npm test"
    print("PASS: test_6 destructive/cloud/db commands blocked")


def test_7_can_spawn_helper_on_separate_branch():
    guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    result = guards.validate_git_commit("feature-branch/helper-1")
    assert result.allowed
    result = guards.validate_session_start()
    assert result.allowed
    print("PASS: test_7 can spawn helper on separate branch")


def test_8_session_start_validation():
    good_guards = AutonomyGuardChain(WORKTREE, "feature-branch")
    assert good_guards.validate_session_start().allowed

    bad_branch_guards = AutonomyGuardChain(WORKTREE, "main")
    assert not bad_branch_guards.validate_session_start().allowed

    bad_path_guards = AutonomyGuardChain("/tmp/random", "feature-branch")
    assert not bad_path_guards.validate_session_start().allowed
    print("PASS: test_8 session start validation works")


if __name__ == "__main__":
    test_1_agent_can_edit_files_in_worktree()
    test_2_agent_can_commit()
    test_3_cannot_write_outside_worktree()
    test_4_cannot_modify_secrets()
    test_5_cannot_push_to_main()
    test_6_cannot_run_destructive_db_commands()
    test_7_can_spawn_helper_on_separate_branch()
    test_8_session_start_validation()
    print("\nAll 8 Full Autonomy Branch tests passed.")
