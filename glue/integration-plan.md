# Integration Plan

## Phase 1: Current Implementation (This Sprint)

### Deliverables
1. UI Bridge Service (FastAPI on :9876)
2. Browser Extension (Chrome MV3)
3. Session Registry CLI (`glue`)
4. Test Application (Vite React)
5. Context handoff files (JSONL + Markdown)

### Integration Points

```
element-source (npm) → browser extension → bridge service → session context → agent
      ↑                       ↑                   ↑              ↑           ↑
   installed            loaded in Chrome       running       file written   reads .md
```

### Steps
1. Install element-source npm package, bundle global build
2. Deploy bridge service on server (uvicorn)
3. Load extension in Chrome (developer mode)
4. Create test session via `glue session create`
5. Open test app in Chrome
6. Inspect element → verify event arrives at bridge → verify context file written

## Phase 2: Deep OpenHands Integration (Future)

### Goal
Agent automatically reads UI context and acts on it.

### Approach
- Mount session context directory into OpenHands workspace
- Add UI context to agent system prompt
- Trigger agent action on new UI events (webhook or file watch)

### OpenHands Integration Options
1. **File-based (simplest):** Place `latest-ui-context.md` in OpenHands workspace mount. Agent reads it when prompted.
2. **API-based:** Use OpenHands API to inject context into active conversation.
3. **Custom microagent:** Create OpenHands microagent that monitors UI events and acts.

## Phase 3: Multi-Agent Routing (Future)

### Goal
Multiple agents working on different features, each receiving UI context for their own feature.

### Approach
- Session registry maps port ranges to agent sessions
- Bridge service routes events by port → session
- Each agent only sees events from their own worktree's dev server

## Upstream Dependency Management

### element-source
- **Install:** `npm install element-source` (or use CDN/bundled global)
- **Update:** Check npm for new versions, rebuild extension
- **Risk:** Breaking API changes (mitigated: pin version)

### par
- **Install:** `pipx install par-cli` (from PyPI) or `pipx install .` (from source)
- **Update:** `pipx upgrade par-cli`
- **Risk:** Python version incompatibility (mitigated: tested on 3.14)

### FastAPI/uvicorn
- **Install:** `pip install fastapi uvicorn`
- **Update:** Standard pip upgrade
- **Risk:** None significant
