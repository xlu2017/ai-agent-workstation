#!/usr/bin/env python3
"""
Multi-Agent PR Courtroom — Specialist reviewer agents for PRs.

Before a PR is opened, this orchestrator runs specialist agents that each
review the changes from their expertise. Results are collected as review
artifacts and a merge decision is made.

Specialists:
  - implementer: code quality, patterns, naming, correctness
  - reviewer: architecture, design, coupling, complexity
  - test_engineer: test coverage, edge cases, test quality
  - security_reviewer: auth, injection, secrets, OWASP
  - migration_reviewer: DB changes, backward compatibility
  - ux_reviewer: accessibility, UX patterns, responsiveness

Each specialist gets the same diff + session context but different system prompts.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", "/opt/workstation/sessions"))
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

SPECIALISTS = {
    "implementer": {
        "role": "Senior Implementation Reviewer",
        "focus": "code quality, patterns, naming, correctness, DRY, SOLID",
        "prompt": """You are a senior implementation reviewer. Focus on:
- Code correctness and logic errors
- Naming conventions and readability
- DRY/SOLID principle violations
- Performance concerns
- Error handling completeness
- Edge cases missed

Review the diff and provide specific, actionable feedback. Reference exact file:line locations.""",
    },
    "reviewer": {
        "role": "Architecture Reviewer",
        "focus": "design, coupling, complexity, separation of concerns",
        "prompt": """You are an architecture reviewer. Focus on:
- Module coupling and cohesion
- Separation of concerns
- Abstraction levels
- API design and contracts
- Scalability implications
- Technical debt introduction

Review the diff and assess architectural impact. Flag design-level concerns.""",
    },
    "test_engineer": {
        "role": "Test Engineering Reviewer",
        "focus": "coverage, edge cases, test quality, regression risk",
        "prompt": """You are a test engineering reviewer. Focus on:
- Test coverage for new/changed code
- Missing edge cases
- Test quality (assertions, isolation, determinism)
- Regression risk assessment
- Integration test needs
- Mock/stub appropriateness

Review the diff and identify testing gaps. Suggest specific test cases.""",
    },
    "security_reviewer": {
        "role": "Security Reviewer",
        "focus": "auth, injection, secrets, OWASP top 10",
        "prompt": """You are a security reviewer. Focus on:
- Authentication/authorization gaps
- Injection vulnerabilities (SQL, XSS, command injection)
- Secrets or credentials in code
- Input validation
- OWASP Top 10 violations
- Dependency vulnerabilities
- Rate limiting and DoS exposure

Review the diff and flag security concerns with severity ratings.""",
    },
    "migration_reviewer": {
        "role": "Migration/Compatibility Reviewer",
        "focus": "backward compatibility, data migrations, API contracts",
        "prompt": """You are a migration and compatibility reviewer. Focus on:
- Database schema changes and migration safety
- API backward compatibility
- Breaking changes for consumers
- Data loss risk
- Rollback strategy
- Feature flag needs

Review the diff and assess deployment safety.""",
    },
    "ux_reviewer": {
        "role": "UX/Accessibility Reviewer",
        "focus": "accessibility, UX patterns, responsive design",
        "prompt": """You are a UX and accessibility reviewer. Focus on:
- WCAG accessibility compliance
- Keyboard navigation
- Screen reader compatibility
- Responsive design
- Loading states and error states
- User feedback and affordances
- Consistent patterns

Review the diff and flag UX/accessibility issues.""",
    },
}


def get_diff(repo_path, base_branch="main"):
    """Get the git diff for review."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_branch}...HEAD"],
            capture_output=True, text=True, cwd=repo_path, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout[:50000]  # Cap at 50KB
        # Fallback to uncommitted changes
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=repo_path, timeout=30,
        )
        return result.stdout[:50000]
    except Exception as e:
        return f"Error getting diff: {e}"


def get_changed_files(repo_path, base_branch="main"):
    """Get list of changed files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            capture_output=True, text=True, cwd=repo_path, timeout=10,
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []


def call_llm(system_prompt, user_prompt, model="deepseek-v4-flash"):
    """Call LLM via LiteLLM proxy."""
    import urllib.request

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    headers = {
        "Content-Type": "application/json",
    }
    if LITELLM_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_KEY}"

    req = urllib.request.Request(
        f"{LITELLM_URL}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[LLM call failed: {e}]"


def run_specialist(specialist_id, diff, changed_files, context=""):
    """Run a single specialist reviewer."""
    spec = SPECIALISTS[specialist_id]
    user_prompt = f"""## Changed Files
{chr(10).join(f'- {f}' for f in changed_files[:20])}

## Diff
```diff
{diff[:30000]}
```

{f'## Additional Context{chr(10)}{context}' if context else ''}

Please provide your review as the {spec['role']}. Focus on: {spec['focus']}.
Use this format:
- severity: critical|warning|info
- file and line if applicable
- specific recommendation
"""
    response = call_llm(spec["prompt"], user_prompt)
    return {
        "specialist": specialist_id,
        "role": spec["role"],
        "focus": spec["focus"],
        "review": response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_courtroom(session_id, repo_path=None, base_branch="main", specialists=None):
    """Run the full PR courtroom review process."""
    session_dir = SESSIONS_DIR / session_id

    if not repo_path:
        meta_file = session_dir / "session.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            repo_path = meta.get("worktree_path") or meta.get("repo_path")

    if not repo_path:
        return {"error": "No repo path found for session."}

    diff = get_diff(repo_path, base_branch)
    changed_files = get_changed_files(repo_path, base_branch)

    if not diff.strip():
        return {"error": "No diff found. Nothing to review."}

    # Select specialists based on changed files
    if specialists is None:
        specialists = ["implementer", "reviewer", "test_engineer", "security_reviewer"]
        # Add migration reviewer if DB/API changes detected
        for f in changed_files:
            if any(x in f.lower() for x in ["migration", "schema", "model", "api"]):
                specialists.append("migration_reviewer")
                break
        # Add UX reviewer if frontend changes
        for f in changed_files:
            if any(f.endswith(ext) for ext in [".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss"]):
                specialists.append("ux_reviewer")
                break

    specialists = list(set(specialists))

    # Load additional context
    context = ""
    terminal_ctx = session_dir / "context" / "latest-terminal-context.md"
    if terminal_ctx.exists():
        context += terminal_ctx.read_text() + "\n"

    # Run each specialist
    reviews = []
    for spec_id in specialists:
        if spec_id in SPECIALISTS:
            review = run_specialist(spec_id, diff, changed_files, context)
            reviews.append(review)

    # Generate merge decision
    all_reviews = "\n\n---\n\n".join(
        f"## {r['role']}\n{r['review']}" for r in reviews
    )
    decision_prompt = f"""Based on these specialist reviews, make a merge decision.

{all_reviews}

Respond with:
1. DECISION: merge / revise / block
2. SUMMARY: One paragraph explaining why
3. BLOCKERS: Critical issues that must be fixed (if any)
4. SUGGESTIONS: Non-blocking improvements
"""
    decision_response = call_llm(
        "You are a merge decision maker. Synthesize specialist reviews into a final verdict.",
        decision_prompt,
    )

    result = {
        "session_id": session_id,
        "repo_path": repo_path,
        "base_branch": base_branch,
        "changed_files": changed_files,
        "specialists_run": specialists,
        "reviews": reviews,
        "decision": decision_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save result
    output_dir = session_dir / "reviews"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"courtroom-{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    # Save markdown summary
    md_file = output_dir / f"courtroom-{int(time.time())}.md"
    md_content = generate_courtroom_md(result)
    with open(md_file, "w") as f:
        f.write(md_content)

    return result


def generate_courtroom_md(result):
    """Generate markdown summary of courtroom review."""
    lines = [
        "# PR Courtroom Review",
        f"**Session:** {result['session_id']}",
        f"**Time:** {result['timestamp']}",
        f"**Changed files:** {len(result['changed_files'])}",
        "",
        "---",
        "",
    ]

    for review in result["reviews"]:
        lines.extend([
            f"## {review['role']}",
            f"*Focus: {review['focus']}*",
            "",
            review["review"],
            "",
            "---",
            "",
        ])

    lines.extend([
        "## Merge Decision",
        "",
        result["decision"],
    ])

    return "\n".join(lines)


# --- MCP Tools ---

TOOLS = [
    {
        "name": "run_courtroom",
        "description": "Run the full multi-agent PR courtroom review. Specialist agents review the diff from different perspectives and produce a merge decision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID containing the changes."},
                "repo_path": {"type": "string", "description": "Repo/worktree path (optional, auto-detected from session)."},
                "base_branch": {"type": "string", "description": "Base branch to diff against (default: main)."},
                "specialists": {"type": "array", "items": {"type": "string"}, "description": "Specific specialists to run (optional, auto-detected)."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "run_specialist",
        "description": "Run a single specialist reviewer on the current diff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specialist": {"type": "string", "enum": list(SPECIALISTS.keys()), "description": "Which specialist to run."},
                "session_id": {"type": "string", "description": "Session ID."},
            },
            "required": ["specialist", "session_id"],
        },
    },
    {
        "name": "list_specialists",
        "description": "List available specialist reviewers and their focus areas.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_review",
        "description": "Get the most recent courtroom review for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID."},
            },
            "required": ["session_id"],
        },
    },
]


def handle_run_courtroom(args):
    result = run_courtroom(
        session_id=args.get("session_id", ""),
        repo_path=args.get("repo_path"),
        base_branch=args.get("base_branch", "main"),
        specialists=args.get("specialists"),
    )
    if "error" in result:
        return {"content": [{"type": "text", "text": result["error"]}]}
    md = generate_courtroom_md(result)
    return {"content": [{"type": "text", "text": md}]}


def handle_run_specialist(args):
    session_id = args.get("session_id", "")
    specialist = args.get("specialist", "")
    session_dir = SESSIONS_DIR / session_id
    meta_file = session_dir / "session.json"
    repo_path = None
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        repo_path = meta.get("worktree_path") or meta.get("repo_path")
    if not repo_path:
        return {"content": [{"type": "text", "text": "No repo path for session."}]}
    diff = get_diff(repo_path)
    changed_files = get_changed_files(repo_path)
    review = run_specialist(specialist, diff, changed_files)
    return {"content": [{"type": "text", "text": f"## {review['role']}\n\n{review['review']}"}]}


def handle_list_specialists(args):
    lines = ["## Available Specialists\n"]
    for sid, spec in SPECIALISTS.items():
        lines.append(f"- **{sid}**: {spec['role']} — {spec['focus']}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def handle_get_review(args):
    session_id = args.get("session_id", "")
    reviews_dir = SESSIONS_DIR / session_id / "reviews"
    if not reviews_dir.exists():
        return {"content": [{"type": "text", "text": "No reviews found."}]}
    md_files = sorted(reviews_dir.glob("courtroom-*.md"), reverse=True)
    if md_files:
        return {"content": [{"type": "text", "text": md_files[0].read_text()}]}
    return {"content": [{"type": "text", "text": "No courtroom reviews found."}]}


# --- MCP Protocol ---

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
            "serverInfo": {"name": "pr-courtroom-mcp", "version": "0.1.0"},
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handlers = {
            "run_courtroom": handle_run_courtroom,
            "run_specialist": handle_run_specialist,
            "list_specialists": handle_list_specialists,
            "get_review": handle_get_review,
        }
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {name}"}}
        return {"jsonrpc": "2.0", "id": id, "result": handler(args)}
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": id, "result": {}}
    return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"Unknown: {method}"}}


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
            sys.stderr.write(f"PR Courtroom MCP error: {e}\n")


if __name__ == "__main__":
    main()
