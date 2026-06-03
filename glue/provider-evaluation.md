# Upstream Project Evaluation

## Summary Table

| Project | Language | License | Maintenance | Reuse Decision | Role |
|---------|----------|---------|-------------|----------------|------|
| element-source | TypeScript | MIT | Active (Mar 2026) | **npm dependency** | Core source resolution |
| par | Python | No formal license (LICENSE.txt exists) | Active (2025) | **Install via pipx** | Session/worktree manager |
| workmux | Rust | MIT | Active (2025) | Reference only | Alternative session manager |
| agent-deck | Go | MIT | Active (2025) | Reference only | TUI/MCP reference |
| react-dev-inspector | TypeScript | MIT | Maintained | Reference only | React inspection ideas |
| click-to-component | TypeScript | MIT | Maintained | Reference only | Click-to-source ideas |
| source-map-explorer | TypeScript | Apache-2.0 | Maintained | Reference only | Source map analysis |
| OpenHands | Python | MIT | Very active | Already deployed | Agent runtime |

## Detailed Evaluations

### 1. element-source (aidenybai/element-source)

- **URL:** https://github.com/aidenybai/element-source
- **License:** MIT
- **Language:** TypeScript (monorepo via pnpm + turbo)
- **Stars:** 413
- **Last updated:** March 2026
- **Key dependency:** `bippy` (React fiber introspection)

**What it does:**
Pass any DOM element to `resolveElementInfo()` and get: component name, source file path, line number, column number, and full component stack. Works with React, Preact, Vue, Svelte, and Solid.

**API:**
```ts
const info = await resolveElementInfo(element);
// { tagName, componentName, source: { filePath, lineNumber, columnNumber }, stack: [...] }
```

**Decision: USE as npm dependency in browser extension.**
- Provides exactly the source resolution we need
- Multi-framework support out of the box
- Clean API, small bundle
- Published as `element-source` on npm with global build (`dist/index.global.js`)

**Integration approach:**
- Bundle `element-source` global build into the browser extension
- Inject into page context (needs access to React fibers in main world)
- Call `resolveElementInfo()` when user inspects an element
- Forward result to bridge service

**Risks:**
- Depends on framework debug metadata (only works in dev mode)
- `bippy` dependency may add bundle size
- Async API means slight delay on resolution

---

### 2. par (coplane/par)

- **URL:** https://github.com/coplane/par
- **License:** No formal LICENSE file (LICENSE.txt present but may be incomplete)
- **Language:** Python (uses uv, typer CLI)
- **Version:** 0.2.2
- **Last updated:** 2025

**What it does:**
Global CLI for managing parallel git worktrees and tmux sessions. Purpose-built for AI coding agents. Creates isolated development environments with labels.

**Key commands:**
```bash
par create <label>        # worktree + branch + tmux session
par list                  # show all sessions
par destroy <label>       # clean up everything
par send <label> "cmd"    # send command to session
par workspace create      # multi-repo workspaces
```

**Decision: INSTALL directly via pipx.**
- Perfect fit for our session management needs
- Already handles worktrees + tmux + labels
- Python = easy to extend
- Installed and working on server

**Integration approach:**
- Use `par create/destroy/list` as the backend for `glue session` commands
- Our session registry adds: port allocation, browser profiles, context dirs, bridge routing
- par handles the git/tmux complexity; we add the agent-specific metadata layer

**Risks:**
- No formal license may be an issue for redistribution
- Python 3.14 compatibility (tested, works)
- tmux must be installed (already is)

---

### 3. workmux (raine/workmux)

- **URL:** https://github.com/raine/workmux
- **License:** MIT
- **Language:** Rust
- **Last updated:** 2025

**What it does:**
Similar to par — git worktrees + tmux windows as isolated dev environments. More opinionated (YAML config per project). Also supports zellij and kitty.

**Decision: Reference only.**
- Rust binary = harder to extend
- par covers the same use case in Python (easier integration)
- YAML config approach is interesting but not needed for our dynamic session model

**What we take:** The `.workmux.yaml` per-project config idea for future enhancement.

---

### 4. agent-deck (asheshgoplani/agent-deck)

- **URL:** https://github.com/asheshgoplani/agent-deck
- **License:** MIT
- **Language:** Go
- **Last updated:** 2025

**What it does:**
"AI agent command center" — TUI dashboard, tmux session management, MCP pooling, multi-agent orchestration. More ambitious than par.

**Decision: Reference only.**
- Go binary = harder to extend dynamically
- MCP pooling concept is interesting but premature for us
- par is simpler and sufficient for current needs
- TUI dashboard is nice but not needed yet

**What we take:** The "conductor" concept for future RFC on multi-agent scheduling.

---

### 5. react-dev-inspector (zthxxx/react-dev-inspector)

- **URL:** https://github.com/zthxxx/react-dev-inspector
- **License:** MIT
- **Language:** TypeScript

**What it does:**
Click any React component in browser → opens source file in IDE. Requires a Vite/webpack plugin to inject `__source` annotations at build time.

**Decision: Reference only.**
- Requires build plugin (invasive to target project)
- element-source achieves similar goal without build plugins
- IDE integration concepts are useful for future work

---

### 6. click-to-component (ericclemmons/click-to-component)

- **URL:** https://github.com/ericclemmons/click-to-component
- **License:** MIT
- **Language:** TypeScript

**What it does:**
Alt+Click any element → opens in VS Code. Works with Next.js, CRA, Vite. Uses React fiber `_debugSource` for resolution.

**Decision: Reference only.**
- Similar approach to element-source but React-only
- element-source is more complete (multi-framework, better API)
- IDE-opening logic is reference for future feature

---

### 7. source-map-explorer (danvk/source-map-explorer)

- **URL:** https://github.com/danvk/source-map-explorer
- **License:** Apache-2.0
- **Language:** TypeScript

**What it does:**
Analyzes JavaScript source maps to show bundle composition. Visualization tool, not runtime resolution.

**Decision: Reference only.**
- Different use case (bundle analysis vs runtime element resolution)
- May be useful if we need to do offline source map parsing in the bridge service
- For now, element-source handles runtime resolution directly

---

### 8. OpenHands (All-Hands-AI/OpenHands)

- **URL:** https://github.com/All-Hands-AI/OpenHands
- **License:** MIT
- **Language:** Python + TypeScript

**What it does:**
AI coding agent framework. Already deployed on the workstation.

**Decision: Already in use. Reference for integration patterns.**
- Workspace files are at `/opt/workspace_base` inside the container
- Can read files placed in the workspace mount
- Future: use OpenHands API for programmatic session management

**Integration approach:**
- Place `latest-ui-context.md` in a location OpenHands can read
- Map session context directories to OpenHands workspace mounts
- Document but don't implement deep API integration yet
