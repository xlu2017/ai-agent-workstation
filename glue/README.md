# Workstation Glue Layer

Source-aware multi-agent session management for the AI coding workstation. Connects browser UI inspection to coding agent sessions via source-file resolution.

## What It Does

1. You inspect a UI element in Chrome (right-click → "Inspect element for agent")
2. The browser extension resolves the element to its source file/component using [element-source](https://github.com/aidenybai/element-source)
3. The event is sent to the UI Bridge service
4. The bridge routes the context to the correct agent session
5. A markdown context file is written that the agent can read

## Quick Start

```bash
# Start the bridge service
cd /opt/workstation/glue/ui-bridge
uvicorn server:app --host 0.0.0.0 --port 9876

# Create a session
glue session create my-feature --repo /opt/workstation/repos/my-app

# Load the browser extension
# Chrome → chrome://extensions → Developer mode → Load unpacked → /opt/workstation/glue/browser-extension

# Open your dev app in Chrome
# Right-click any element → "Inspect element for agent"
# Check: /opt/workstation/sessions/my-feature/context/latest-ui-context.md
```

## Components

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| UI Bridge Service | `ui-bridge/server.py` | 9876 | Event router + context writer |
| Browser Extension | `browser-extension/` | — | Element capture + source resolution |
| Session CLI | `bin/glue` | — | Session lifecycle management |
| Test App | `test-app/` | 5180 | Vite React app for validation |

## Dependencies

| Upstream Project | How Used | Install |
|-----------------|----------|---------|
| [element-source](https://github.com/aidenybai/element-source) | npm package, bundled in extension | `npm install element-source` |
| [par](https://github.com/coplane/par) | Session/worktree management | `pipx install par-cli` |
| FastAPI | Bridge service framework | `pip install fastapi uvicorn` |

## Directory Structure

```
/opt/workstation/
├── glue/
│   ├── ui-bridge/          # Bridge service (FastAPI)
│   ├── browser-extension/  # Chrome MV3 extension
│   ├── test-app/           # Vite React test application
│   ├── bin/glue            # CLI tool
│   └── docs/               # Documentation
├── sessions/               # Per-session metadata + context
│   └── <session-id>/
│       ├── session.json
│       └── context/
│           ├── ui-events.jsonl
│           └── latest-ui-context.md
└── upstream/               # Cloned reference projects (read-only)
```

## Session Management

```bash
glue session list                    # List all sessions
glue session create <name>           # Create with worktree + tmux
glue session destroy <name>          # Clean up everything
glue session inspect <name>          # Show details + latest context
glue bridge start                    # Start UI bridge service
glue bridge status                   # Check bridge health
```

## Supported Frameworks

Source resolution works with (via element-source):
- React (including Next.js)
- Preact
- Vue
- Svelte
- Solid

**Requirement:** App must be running in development mode (debug metadata needed).
