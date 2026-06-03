#!/usr/bin/env python3
"""
Serena-style Code Intelligence MCP Server — Per-session symbol graph.

Provides code navigation and understanding tools using tree-sitter
for parsing and ripgrep for search. Each session gets an isolated
view scoped to its worktree.

MCP Tools:
  find_symbol        — Find symbol definition (function, class, variable)
  find_references    — Find all references to a symbol
  get_file_symbols   — List all symbols in a file
  get_call_graph     — Get callers/callees of a function
  search_code        — Semantic-aware code search
  get_imports        — Get import graph for a file
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))


def get_worktree_for_session(session_id):
    """Get the worktree/repo path for a session."""
    meta_file = SESSIONS_DIR / session_id / "session.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        return meta.get("worktree_path") or meta.get("repo_path") or ""
    return ""


def ripgrep(pattern, path, flags=None):
    """Run ripgrep and return matches."""
    cmd = ["rg", "--json", pattern]
    if flags:
        cmd.extend(flags)
    cmd.append(str(path))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    matches.append({
                        "file": match_data["path"]["text"],
                        "line": match_data["line_number"],
                        "text": match_data["lines"]["text"].strip(),
                    })
            except json.JSONDecodeError:
                continue
        return matches
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def find_symbol_definitions(symbol, path, language=None):
    """Find where a symbol is defined."""
    patterns = {
        "python": [
            rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
            rf"^{re.escape(symbol)}\s*=",
        ],
        "javascript": [
            rf"^\s*(export\s+)?(const|let|var|function|class)\s+{re.escape(symbol)}\b",
            rf"^\s*(export\s+)?default\s+(function|class)\s+{re.escape(symbol)}\b",
        ],
        "typescript": [
            rf"^\s*(export\s+)?(const|let|var|function|class|interface|type|enum)\s+{re.escape(symbol)}\b",
        ],
        "rust": [
            rf"^\s*(pub\s+)?(fn|struct|enum|trait|type|const|static|mod)\s+{re.escape(symbol)}\b",
        ],
        "go": [
            rf"^\s*(func|type|var|const)\s+{re.escape(symbol)}\b",
        ],
    }

    all_patterns = []
    if language and language in patterns:
        all_patterns = patterns[language]
    else:
        for lang_patterns in patterns.values():
            all_patterns.extend(lang_patterns)

    results = []
    for pattern in all_patterns:
        matches = ripgrep(pattern, path, ["-n", "--no-heading"])
        results.extend(matches)

    return results


def find_references(symbol, path):
    """Find all references to a symbol."""
    pattern = rf"\b{re.escape(symbol)}\b"
    return ripgrep(pattern, path, ["-n", "--no-heading", "-w"])


def get_file_symbols(filepath):
    """Extract symbols from a file using regex patterns."""
    if not Path(filepath).exists():
        return []

    content = Path(filepath).read_text()
    ext = Path(filepath).suffix

    symbols = []
    patterns = []

    if ext in (".py",):
        patterns = [
            (r"^\s*def\s+(\w+)", "function"),
            (r"^\s*class\s+(\w+)", "class"),
            (r"^(\w+)\s*=", "variable"),
        ]
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        patterns = [
            (r"^\s*(?:export\s+)?(?:default\s+)?function\s+(\w+)", "function"),
            (r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", "class"),
            (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)", "variable"),
            (r"^\s*(?:export\s+)?(?:interface|type)\s+(\w+)", "type"),
        ]
    elif ext in (".rs",):
        patterns = [
            (r"^\s*(?:pub\s+)?fn\s+(\w+)", "function"),
            (r"^\s*(?:pub\s+)?struct\s+(\w+)", "struct"),
            (r"^\s*(?:pub\s+)?enum\s+(\w+)", "enum"),
            (r"^\s*(?:pub\s+)?trait\s+(\w+)", "trait"),
        ]
    elif ext in (".go",):
        patterns = [
            (r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", "function"),
            (r"^type\s+(\w+)\s+struct", "struct"),
            (r"^type\s+(\w+)\s+interface", "interface"),
        ]

    for i, line in enumerate(content.split("\n"), 1):
        for pattern, kind in patterns:
            match = re.match(pattern, line)
            if match:
                symbols.append({
                    "name": match.group(1),
                    "kind": kind,
                    "line": i,
                    "text": line.strip(),
                })

    return symbols


def get_imports(filepath):
    """Get imports from a file."""
    if not Path(filepath).exists():
        return []

    content = Path(filepath).read_text()
    ext = Path(filepath).suffix
    imports = []

    if ext in (".py",):
        for i, line in enumerate(content.split("\n"), 1):
            match = re.match(r"^\s*(from\s+\S+\s+import\s+.+|import\s+.+)", line)
            if match:
                imports.append({"line": i, "text": match.group(1).strip()})

    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        for i, line in enumerate(content.split("\n"), 1):
            match = re.match(r"^\s*(import\s+.+)", line)
            if match:
                imports.append({"line": i, "text": match.group(1).strip()})

    elif ext in (".rs",):
        for i, line in enumerate(content.split("\n"), 1):
            match = re.match(r"^\s*(use\s+.+;)", line)
            if match:
                imports.append({"line": i, "text": match.group(1).strip()})

    elif ext in (".go",):
        for i, line in enumerate(content.split("\n"), 1):
            match = re.match(r'^\s*"(.+)"', line)
            if match:
                imports.append({"line": i, "text": f'import "{match.group(1)}"'})

    return imports


def get_call_graph(symbol, path):
    """Get callers and callees of a function."""
    # Find the function definition
    defs = find_symbol_definitions(symbol, path)
    if not defs:
        return {"callers": [], "callees": [], "definition": None}

    definition = defs[0]

    # Find callers: other places that call this symbol
    callers = find_references(symbol, path)
    callers = [c for c in callers if c["file"] != definition["file"] or c["line"] != definition["line"]]

    # Find callees: function calls within this function (approximate)
    callees = []
    if Path(definition["file"]).exists():
        content = Path(definition["file"]).read_text().split("\n")
        start_line = definition["line"] - 1
        indent = len(content[start_line]) - len(content[start_line].lstrip())

        for i in range(start_line + 1, min(start_line + 50, len(content))):
            line = content[i]
            if line.strip() and not line.startswith(" " * (indent + 1)) and i > start_line + 1:
                break
            calls = re.findall(r"(\w+)\s*\(", line)
            for call in calls:
                if call not in ("if", "for", "while", "return", "print", "len", "range", "str", "int"):
                    callees.append({"name": call, "line": i + 1, "file": definition["file"]})

    return {
        "definition": definition,
        "callers": callers[:20],
        "callees": callees[:20],
    }


# --- MCP Tool Handlers ---

def handle_find_symbol(arguments):
    session_id = arguments.get("session_id", "")
    symbol = arguments.get("symbol", "")
    language = arguments.get("language")

    path = get_worktree_for_session(session_id) if session_id else "."
    if not path:
        path = "."

    results = find_symbol_definitions(symbol, path, language)
    if not results:
        return {"content": [{"type": "text", "text": f"No definition found for `{symbol}`."}]}

    lines = [f"## Symbol: `{symbol}`\n"]
    for r in results[:10]:
        lines.append(f"- `{r['file']}:{r['line']}` — `{r['text']}`")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_find_references(arguments):
    session_id = arguments.get("session_id", "")
    symbol = arguments.get("symbol", "")

    path = get_worktree_for_session(session_id) if session_id else "."
    if not path:
        path = "."

    results = find_references(symbol, path)
    if not results:
        return {"content": [{"type": "text", "text": f"No references found for `{symbol}`."}]}

    lines = [f"## References to `{symbol}` ({len(results)} found)\n"]
    for r in results[:30]:
        lines.append(f"- `{r['file']}:{r['line']}` — `{r['text']}`")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_file_symbols(arguments):
    filepath = arguments.get("file", "")
    if not filepath or not Path(filepath).exists():
        return {"content": [{"type": "text", "text": f"File not found: `{filepath}`"}]}

    symbols = get_file_symbols(filepath)
    if not symbols:
        return {"content": [{"type": "text", "text": f"No symbols found in `{filepath}`."}]}

    lines = [f"## Symbols in `{filepath}`\n"]
    for s in symbols:
        lines.append(f"- **{s['kind']}** `{s['name']}` (line {s['line']})")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_call_graph(arguments):
    session_id = arguments.get("session_id", "")
    symbol = arguments.get("symbol", "")

    path = get_worktree_for_session(session_id) if session_id else "."
    if not path:
        path = "."

    graph = get_call_graph(symbol, path)

    lines = [f"## Call Graph: `{symbol}`\n"]
    if graph["definition"]:
        d = graph["definition"]
        lines.append(f"**Definition:** `{d['file']}:{d['line']}`\n")

    if graph["callers"]:
        lines.append(f"### Callers ({len(graph['callers'])})")
        for c in graph["callers"][:15]:
            lines.append(f"- `{c['file']}:{c['line']}` — `{c['text']}`")
    else:
        lines.append("### Callers: none found")

    lines.append("")
    if graph["callees"]:
        lines.append(f"### Callees ({len(graph['callees'])})")
        for c in graph["callees"][:15]:
            lines.append(f"- `{c['name']}` at line {c['line']}")
    else:
        lines.append("### Callees: none found")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_search_code(arguments):
    session_id = arguments.get("session_id", "")
    query = arguments.get("query", "")
    glob = arguments.get("glob")

    path = get_worktree_for_session(session_id) if session_id else "."
    if not path:
        path = "."

    flags = ["-n", "--no-heading", "-i"]
    if glob:
        flags.extend(["--glob", glob])

    results = ripgrep(query, path, flags)
    if not results:
        return {"content": [{"type": "text", "text": f"No results for `{query}`."}]}

    lines = [f"## Search: `{query}` ({len(results)} matches)\n"]
    for r in results[:30]:
        lines.append(f"- `{r['file']}:{r['line']}` — `{r['text']}`")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_imports(arguments):
    filepath = arguments.get("file", "")
    if not filepath or not Path(filepath).exists():
        return {"content": [{"type": "text", "text": f"File not found: `{filepath}`"}]}

    imports = get_imports(filepath)
    if not imports:
        return {"content": [{"type": "text", "text": f"No imports found in `{filepath}`."}]}

    lines = [f"## Imports in `{filepath}`\n"]
    for imp in imports:
        lines.append(f"- Line {imp['line']}: `{imp['text']}`")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# --- MCP Protocol ---

TOOLS = [
    {
        "name": "find_symbol",
        "description": "Find the definition of a symbol (function, class, variable, type) in the codebase.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to find."},
                "session_id": {"type": "string", "description": "Optional session ID to scope search."},
                "language": {"type": "string", "description": "Optional language hint (python, javascript, typescript, rust, go)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "find_references",
        "description": "Find all references to a symbol across the codebase.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to find references for."},
                "session_id": {"type": "string", "description": "Optional session ID to scope search."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_file_symbols",
        "description": "List all symbols (functions, classes, variables, types) defined in a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Absolute or relative file path."},
            },
            "required": ["file"],
        },
    },
    {
        "name": "get_call_graph",
        "description": "Get the call graph for a function: who calls it (callers) and what it calls (callees).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Function name."},
                "session_id": {"type": "string", "description": "Optional session ID to scope search."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "search_code",
        "description": "Search code with regex pattern. More powerful than grep — understands file types.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Regex pattern to search."},
                "session_id": {"type": "string", "description": "Optional session ID."},
                "glob": {"type": "string", "description": "File glob filter (e.g., '*.py', '*.ts')."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_imports",
        "description": "Get the import/dependency graph for a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "File path."},
            },
            "required": ["file"],
        },
    },
]


def read_message():
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    content_length = int(headers.get("content-length", 0))
    if content_length == 0:
        return None
    return json.loads(sys.stdin.read(content_length))


def write_message(msg):
    body = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


def handle_request(msg):
    method = msg.get("method", "")
    id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "serena-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handlers = {
            "find_symbol": handle_find_symbol,
            "find_references": handle_find_references,
            "get_file_symbols": handle_get_file_symbols,
            "get_call_graph": handle_get_call_graph,
            "search_code": handle_search_code,
            "get_imports": handle_get_imports,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        result = handler(arguments)
        return {"jsonrpc": "2.0", "id": id, "result": result}
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": id, "result": {}}
    else:
        return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break
            response = handle_request(msg)
            if response:
                write_message(response)
        except EOFError:
            break
        except Exception as e:
            sys.stderr.write(f"Serena MCP error: {e}\n")


if __name__ == "__main__":
    main()
