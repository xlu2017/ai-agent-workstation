# Glue Layer Architecture

## Overview

The glue layer connects browser-based UI inspection to AI coding agent sessions. When a user selects or inspects an element in Chrome, the system identifies the source file/component and routes that context to the correct agent session.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Chrome Browser                                   │
│                                                                          │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ Target Web App  │    │ element-source   │    │ Browser Extension│  │
│  │ (Vite/React)    │◄───│ (page context)   │◄───│ (content script) │  │
│  │                 │    │                  │    │                  │  │
│  └─────────────────┘    └──────────────────┘    └────────┬─────────┘  │
│                                                           │            │
└───────────────────────────────────────────────────────────┼────────────┘
                                                            │ HTTP POST
                                                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         UI Bridge Service (:9876)                         │
│                                                                          │
│  POST /selection    POST /inspect    GET /events    GET /sessions        │
│                                                                          │
│  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────────┐    │
│  │ Event Log   │   │ Session Router   │   │ Context Writer       │    │
│  │ (JSONL)     │   │ (port→session)   │   │ (MD + JSONL files)   │    │
│  └─────────────┘   └──────────────────┘   └──────────────────────┘    │
└──────────────────────────────────────────────────────┬──────────────────┘
                                                       │
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Session Context Files                                  │
│                                                                          │
│  /opt/workstation/sessions/<session_id>/                                 │
│  ├── session.json              (metadata: repo, branch, ports, tmux)    │
│  └── context/                                                            │
│      ├── ui-events.jsonl       (append-only event log)                  │
│      └── latest-ui-context.md  (human/agent-readable current context)   │
│                                                                          │
└──────────────────────────────────────────────────────┬──────────────────┘
                                                       │
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Agent Sessions                                         │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐               │
│  │ OpenHands    │   │ tmux session │   │ par worktree │               │
│  │ (reads .md)  │   │ (CLI access) │   │ (git branch) │               │
│  └──────────────┘   └──────────────┘   └──────────────┘               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Browser Extension (Chrome MV3)
- **content.js** — Runs in content script context. Captures element metadata, XPath, text.
- **element-source-page.js** — Injected into page context (main world). Uses element-source library to resolve React/Vue/Svelte fibers to source locations.
- **background.js** — Service worker. Forwards events to bridge service. Manages context menus.
- **popup.html** — Quick access UI with bridge status and inspect button.

### 2. UI Bridge Service (FastAPI, Python)
- Receives events from browser extension
- Routes events to correct session based on port mapping
- Writes JSONL event log (global)
- Writes per-session context files
- Generates `latest-ui-context.md` for agent consumption

### 3. Session Registry (`glue` CLI)
- Wraps `par` for worktree/tmux management
- Adds agent-specific metadata: port ranges, browser profiles, context dirs
- Stores JSON metadata in `/opt/workstation/sessions/<id>/session.json`
- Provides `glue session list|create|destroy|inspect` commands

### 4. Source Mapping Adapter
- **Primary:** element-source (runtime, multi-framework)
- **Fallback:** Direct React fiber `_debugSource` inspection
- **Future:** Source map file parsing for production builds

## Session Routing

Events are routed to sessions based on the port of the target web app:

```
Port 5180 → session-port-5180 → /opt/workstation/sessions/session-port-5180/
Port 5190 → session-port-5190 → /opt/workstation/sessions/session-port-5190/
```

Each session's port range is recorded in `session.json`. The bridge service maps incoming events to sessions by matching the URL port.

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Bridge service | Python + FastAPI | Fast to build, matches server Python ecosystem |
| Browser extension | JavaScript (MV3) | Chrome extension requirement |
| Source resolution | element-source (npm) | Best-in-class multi-framework resolution |
| Session management | par (Python CLI) | Purpose-built for agent worktrees |
| Context format | Markdown + JSONL | Agent-readable, append-friendly |
| Communication | HTTP + JSON | Simple, debuggable, no custom protocols |

## Limitations

1. **Dev mode only** — element-source reads framework debug metadata (React fibers, Vue internals). This is only available in development builds.
2. **localhost only** — Extension only activates on localhost URLs.
3. **Async resolution** — Source resolution may take up to 500ms. Events are sent with a fallback if resolution times out.
4. **No production source maps** — Future: parse `.map` files for production builds.
5. **Single machine** — All components run on the same server. No distributed architecture yet.
