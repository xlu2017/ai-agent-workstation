"""
Autonomy Guards — validation layer for Full Autonomy Branch Mode.

Guards:
- BranchGuard: prevents operations on protected branches
- PathGuard: enforces worktree boundary
- SecretGuard: blocks access to secrets/credentials
- DestructiveCommandGuard: blocks rm -rf, mkfs, etc.
- CloudCommandGuard: blocks cloud resource creation
- DatabaseCommandGuard: blocks destructive DB operations
"""

import re
from pathlib import Path
from typing import Optional

PROTECTED_BRANCHES = ["main", "master", "develop", "production"]

ALLOWED_WORKTREE_ROOTS = [
    "/opt/workstation/repos",
    "/opt/workstation/sessions",
]

SECRET_PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"credentials",
    r"secrets",
    r"\.pem$",
    r"\.key$",
    r"id_rsa",
    r"\.ssh/",
    r"api[_-]?key",
    r"token",
]

DESTRUCTIVE_COMMANDS = [
    r"rm\s+-rf\s+/",
    r"sudo\s+rm",
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/",
    r"shutdown",
    r"reboot",
    r"systemctl\s+(stop|disable)\s+(docker|ssh|network)",
    r"chmod\s+-R\s+777\s+/",
    r"chown\s+-R.*\s+/",
]

CLOUD_COMMANDS = [
    r"aws\s+\S+\s+create",
    r"aws\s+\S+\s+delete",
    r"aws\s+\S+\s+terminate",
    r"gcloud\s+\S+\s+create",
    r"gcloud\s+\S+\s+delete",
    r"az\s+\S+\s+create",
    r"az\s+\S+\s+delete",
    r"terraform\s+apply",
    r"terraform\s+destroy",
    r"pulumi\s+up",
    r"pulumi\s+destroy",
]

DATABASE_COMMANDS = [
    r"DROP\s+DATABASE",
    r"DROP\s+TABLE",
    r"DROP\s+SCHEMA",
    r"TRUNCATE\s+TABLE",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",
    r"ALTER\s+TABLE.*DROP",
    r"pg_dump.*--clean",
    r"mongodump.*--drop",
]


class GuardResult:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

    def __bool__(self):
        return self.allowed


class BranchGuard:
    """Prevents operations on protected branches."""

    def __init__(self, protected: list = None):
        self.protected = protected or PROTECTED_BRANCHES

    def check(self, branch: str, operation: str = "modify") -> GuardResult:
        if branch in self.protected:
            return GuardResult(False, f"Cannot {operation} on protected branch: {branch}")
        return GuardResult(True)

    def check_push(self, branch: str) -> GuardResult:
        if branch in self.protected:
            return GuardResult(False, f"Push to protected branch blocked: {branch}")
        return GuardResult(True)

    def check_force_push(self, branch: str) -> GuardResult:
        return GuardResult(False, f"Force push blocked on all branches in autonomy mode: {branch}")


class PathGuard:
    """Enforces strict worktree boundary for file operations.

    Only allows access within the session's own worktree directory.
    The allowed_roots are used only to validate that the worktree itself
    is under an acceptable parent — not to grant broad access.
    """

    def __init__(self, worktree: str, allowed_roots: list = None):
        self.worktree = Path(worktree).resolve()
        self.allowed_roots = allowed_roots or ALLOWED_WORKTREE_ROOTS

    def check(self, target_path: str) -> GuardResult:
        resolved = Path(target_path).resolve()
        if str(resolved).startswith(str(self.worktree) + "/") or resolved == self.worktree:
            return GuardResult(True)
        return GuardResult(False, f"Path outside worktree boundary: {target_path}")

    def check_delete(self, target_path: str) -> GuardResult:
        resolved = Path(target_path).resolve()
        if not (str(resolved).startswith(str(self.worktree) + "/") or resolved == self.worktree):
            return GuardResult(False, f"Cannot delete outside worktree: {target_path}")
        if resolved == self.worktree:
            return GuardResult(False, "Cannot delete worktree root")
        return GuardResult(True)

    def check_worktree_root(self, worktree: str) -> GuardResult:
        for root in self.allowed_roots:
            if worktree.startswith(root):
                return GuardResult(True)
        return GuardResult(False, f"Worktree not under allowed roots: {worktree}")


class SecretGuard:
    """Blocks access to secrets and credentials."""

    def __init__(self, patterns: list = None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (patterns or SECRET_PATTERNS)]

    def check_path(self, path: str) -> GuardResult:
        for pattern in self.patterns:
            if pattern.search(path):
                return GuardResult(False, f"Access to potential secret file blocked: {path}")
        return GuardResult(True)

    def check_content(self, content: str) -> GuardResult:
        sensitive_patterns = [
            r"(sk-[a-zA-Z0-9]{20,})",
            r"(AKIA[A-Z0-9]{16})",
            r"(ghp_[a-zA-Z0-9]{36})",
            r"(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)",
        ]
        for pattern in sensitive_patterns:
            if re.search(pattern, content):
                return GuardResult(False, "Content contains potential API key or secret")
        return GuardResult(True)

    def check_command_output(self, command: str) -> GuardResult:
        output_patterns = [
            r"cat\s+.*\.(env|pem|key)",
            r"echo\s+\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)\w*\}?",
            r"printenv.*(KEY|TOKEN|SECRET|PASSWORD)",
            r"env\s*\|\s*grep.*(KEY|TOKEN|SECRET)",
        ]
        for pattern in output_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return GuardResult(False, f"Command may expose secrets: {command}")
        return GuardResult(True)


class DestructiveCommandGuard:
    """Blocks destructive system commands."""

    def __init__(self, patterns: list = None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (patterns or DESTRUCTIVE_COMMANDS)]

    def check(self, command: str) -> GuardResult:
        for pattern in self.patterns:
            if pattern.search(command):
                return GuardResult(False, f"Destructive command blocked: {command[:100]}")
        return GuardResult(True)


class CloudCommandGuard:
    """Blocks cloud resource creation/deletion commands."""

    def __init__(self, patterns: list = None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (patterns or CLOUD_COMMANDS)]

    def check(self, command: str) -> GuardResult:
        for pattern in self.patterns:
            if pattern.search(command):
                return GuardResult(False, f"Cloud operation blocked: {command[:100]}")
        return GuardResult(True)


class DatabaseCommandGuard:
    """Blocks destructive database commands."""

    def __init__(self, patterns: list = None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (patterns or DATABASE_COMMANDS)]

    def check(self, command: str) -> GuardResult:
        for pattern in self.patterns:
            if pattern.search(command):
                return GuardResult(False, f"Destructive database operation blocked: {command[:100]}")
        return GuardResult(True)

    def check_sql(self, sql: str) -> GuardResult:
        return self.check(sql)


class AutonomyGuardChain:
    """Combines all guards into a single validation chain."""

    def __init__(self, worktree: str, branch: str):
        self.branch_guard = BranchGuard()
        self.path_guard = PathGuard(worktree)
        self.secret_guard = SecretGuard()
        self.destructive_guard = DestructiveCommandGuard()
        self.cloud_guard = CloudCommandGuard()
        self.database_guard = DatabaseCommandGuard()
        self.branch = branch
        self.worktree = worktree

    def validate_session_start(self) -> GuardResult:
        """Validate that the session can start in full autonomy mode."""
        branch_check = self.branch_guard.check(self.branch, "execute autonomously on")
        if not branch_check:
            return branch_check
        worktree_check = self.path_guard.check_worktree_root(self.worktree)
        if not worktree_check:
            return worktree_check
        return GuardResult(True)

    def validate_file_read(self, path: str) -> GuardResult:
        path_check = self.path_guard.check(path)
        if not path_check:
            return path_check
        return self.secret_guard.check_path(path)

    def validate_file_write(self, path: str, content: str = "") -> GuardResult:
        path_check = self.path_guard.check(path)
        if not path_check:
            return path_check
        secret_check = self.secret_guard.check_path(path)
        if not secret_check:
            return secret_check
        if content:
            return self.secret_guard.check_content(content)
        return GuardResult(True)

    def validate_file_delete(self, path: str) -> GuardResult:
        return self.path_guard.check_delete(path)

    def validate_command(self, command: str) -> GuardResult:
        destructive_check = self.destructive_guard.check(command)
        if not destructive_check:
            return destructive_check
        cloud_check = self.cloud_guard.check(command)
        if not cloud_check:
            return cloud_check
        db_check = self.database_guard.check(command)
        if not db_check:
            return db_check
        secret_check = self.secret_guard.check_command_output(command)
        if not secret_check:
            return secret_check
        return GuardResult(True)

    def validate_git_push(self, branch: str) -> GuardResult:
        return self.branch_guard.check_push(branch)

    def validate_git_commit(self, branch: str) -> GuardResult:
        return self.branch_guard.check(branch, "commit on")
