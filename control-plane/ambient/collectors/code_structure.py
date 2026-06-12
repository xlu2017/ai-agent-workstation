from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource
from ambient.vendor_registry import ensure_vendor_python_path, provider_available

SUPPORTED_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}


class CodeStructureCollector:
    """Collect lightweight source structure from a repo/worktree.

    Vendored parser libraries are treated as repository-owned implementation
    detail when present, but this collector keeps a fallback path so ambient
    collection remains operational when a vendor is absent.
    """

    def __init__(self, repo_root: str | Path, max_files: int = 80):
        self.repo_root = Path(repo_root)
        self.max_files = max_files

    def build_event(self, session_id: str, *, repo_id: str | None = None, worktree_id: str | None = None, branch: str | None = None) -> AmbientEvent:
        payload = self.snapshot()
        return AmbientEvent(
            event_type=AmbientEventType.REPO_STATE_OBSERVED.value,
            session_id=session_id,
            source=AmbientSource.REPO,
            repo_id=repo_id,
            worktree_id=worktree_id,
            branch=branch,
            confidence=0.8 if payload.get("available") else 0.2,
            payload=payload,
        )

    def snapshot(self) -> dict[str, Any]:
        if not self.repo_root.exists():
            return {"available": False, "provider": "code_structure", "reason": "repo_root_missing", "repo_root": str(self.repo_root)}
        files = list(self._iter_source_files())[: self.max_files]
        symbols: list[dict[str, Any]] = []
        parser_provider = self._parser_provider()
        for path in files:
            symbols.extend(self._extract_symbols(path, parser_provider))
        return {
            "available": True,
            "provider": "code_structure",
            "parser_provider": parser_provider,
            "repo_root": str(self.repo_root),
            "file_count_scanned": len(files),
            "symbols": symbols[:500],
        }

    def _iter_source_files(self):
        ignored = {"node_modules", ".git", ".venv", "dist", "build", "vendor"}
        for path in self.repo_root.rglob("*"):
            if not path.is_file() or path.suffix not in SUPPORTED_SUFFIXES:
                continue
            if any(part in ignored for part in path.parts):
                continue
            yield path

    def _parser_provider(self) -> str:
        ensure_vendor_python_path("tree_sitter")
        return "tree_sitter" if provider_available("tree_sitter", "tree_sitter") else "ast_text"

    def _extract_symbols(self, path: Path, parser_provider: str) -> list[dict[str, Any]]:
        if path.suffix == ".py":
            return self._extract_python_symbols(path)
        return self._extract_text_symbols(path, parser_provider)

    def _extract_python_symbols(self, path: Path) -> list[dict[str, Any]]:
        try:
            text = path.read_text(errors="replace")
            tree = ast.parse(text)
        except Exception:
            return []
        rel = str(path.relative_to(self.repo_root))
        symbols: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append({
                    "path": rel,
                    "name": node.name,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "line": getattr(node, "lineno", None),
                    "end_line": getattr(node, "end_lineno", None),
                    "provider": "python_ast",
                })
        return symbols

    def _extract_text_symbols(self, path: Path, parser_provider: str) -> list[dict[str, Any]]:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            return []
        rel = str(path.relative_to(self.repo_root))
        symbols: list[dict[str, Any]] = []
        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            name = ""
            kind = ""
            if line.startswith("function "):
                name = line[len("function "):].split("(", 1)[0].strip()
                kind = "function"
            elif line.startswith("class "):
                name = line[len("class "):].split(" ", 1)[0].split("{", 1)[0].strip()
                kind = "class"
            elif line.startswith("export function "):
                name = line[len("export function "):].split("(", 1)[0].strip()
                kind = "function"
            elif line.startswith("export class "):
                name = line[len("export class "):].split(" ", 1)[0].split("{", 1)[0].strip()
                kind = "class"
            elif line.startswith("const ") and "=>" in line:
                name = line[len("const "):].split("=", 1)[0].strip()
                kind = "component_or_const"
            elif line.startswith("export const ") and "=>" in line:
                name = line[len("export const "):].split("=", 1)[0].strip()
                kind = "component_or_const"
            if name:
                symbols.append({"path": rel, "name": name, "kind": kind, "line": idx, "provider": parser_provider})
        return symbols
