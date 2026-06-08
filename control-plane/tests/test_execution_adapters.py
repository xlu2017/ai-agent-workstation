"""
Tests for ExecutionAdapter implementations and ExecutionRouter.

Covers:
  9. ExecutionRouter selects agentic executor when configured
  10. ExecutionRouter selects deterministic executor only when explicitly allowed
  11. DeterministicExecutor grep/read_file/run_tests/summarize_diff work in temp repo
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


class TestDeterministicExecutorAdapter:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.wt = Path(self.tmpdir)
        # Set up a minimal git repo
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.tmpdir, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.tmpdir, capture_output=True,
        )
        # Create a test file
        (self.wt / "hello.py").write_text("print('hello world')\n")
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=self.tmpdir, capture_output=True,
        )

        from adapters.execution.fallback_adapter import FallbackExecutorAdapter
        self.adapter = FallbackExecutorAdapter()

    @pytest.mark.asyncio
    async def test_grep_finds_pattern(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "grep",
            {"pattern": "hello"}, {},
        )
        assert result["status"] == "succeeded"
        assert result["backend"] == "deterministic"
        assert result["output"]["count"] > 0

    @pytest.mark.asyncio
    async def test_grep_no_pattern_fails(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "grep", {}, {},
        )
        assert result["status"] == "failed"
        assert "pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_read_file_succeeds(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "read_file",
            {"path": "hello.py"}, {},
        )
        assert result["status"] == "succeeded"
        assert "hello world" in result["output"]["content"]

    @pytest.mark.asyncio
    async def test_read_file_path_traversal_blocked(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "read_file",
            {"path": "../../etc/passwd"}, {},
        )
        assert result["status"] == "failed"
        assert "escapes worktree" in result["error"]

    @pytest.mark.asyncio
    async def test_run_tests_with_echo(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "run_tests",
            {"command": "echo 'tests pass'"}, {},
        )
        assert result["status"] == "succeeded"
        assert "tests pass" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_summarize_diff(self):
        (self.wt / "hello.py").write_text("print('modified')\n")
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "summarize_diff", {}, {},
        )
        assert result["status"] == "succeeded"
        assert "diff_stat" in result["output"]

    @pytest.mark.asyncio
    async def test_commit_with_message(self):
        (self.wt / "new.txt").write_text("new content\n")
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "commit",
            {"message": "add new file"}, {},
        )
        assert result["status"] == "succeeded"
        assert result["output"]["commit_hash"]

    @pytest.mark.asyncio
    async def test_commit_without_message_fails(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "commit",
            {"message": ""}, {},
        )
        assert result["status"] == "failed"
        assert "non-empty message" in result["error"]

    @pytest.mark.asyncio
    async def test_apply_patch_writes_file(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "apply_patch",
            {"file": "new_module.py", "content": "# new module\n"}, {},
        )
        assert result["status"] == "succeeded"
        assert (self.wt / "new_module.py").read_text() == "# new module\n"

    @pytest.mark.asyncio
    async def test_unsupported_action_fails(self):
        result = await self.adapter.execute_action(
            "s1", self.tmpdir, "launch_missile", {}, {},
        )
        assert result["status"] == "failed"
        assert "does not support" in result["error"]


class TestExecutionRouter:
    def test_deterministic_when_allowed(self):
        from adapters.execution.router import ExecutionRouter
        router = ExecutionRouter(
            executor_backend="deterministic",
            allow_deterministic=True,
        )
        assert router.backend_name == "deterministic"

    def test_agentic_when_configured(self):
        from adapters.execution.router import ExecutionRouter
        router = ExecutionRouter(executor_backend="agentic")
        assert router.backend_name == "agentic"

    def test_no_backend_raises(self):
        from adapters.execution.router import ExecutionRouter
        router = ExecutionRouter(
            executor_backend="",
            agentic_enabled=False,
            allow_deterministic=False,
        )
        with pytest.raises(RuntimeError, match="No execution backend configured"):
            router._get_adapter()

    def test_agentic_enabled_default(self):
        from adapters.execution.router import ExecutionRouter
        router = ExecutionRouter(agentic_enabled=True)
        assert router.backend_name == "agentic"

    def test_allow_deterministic_default(self):
        from adapters.execution.router import ExecutionRouter
        router = ExecutionRouter(
            agentic_enabled=False, allow_deterministic=True
        )
        assert router.backend_name == "deterministic"
