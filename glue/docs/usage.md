# Usage Guide

## Basic Workflow

### 1. Create a session for your project

```bash
glue session create my-feature --repo /opt/workstation/repos/my-app --branch feature/navbar
```

This creates:
- A tmux session (`agent-my-feature`)
- A session directory (`/opt/workstation/sessions/my-feature/`)
- A context directory for UI events
- Port allocation for the dev server

### 2. Start your dev server

```bash
# Attach to the session's tmux
tmux attach -t agent-my-feature

# Start dev server (use allocated port)
cd /path/to/worktree
npm run dev -- --port 5180
```

### 3. Open in Chrome and inspect

1. Navigate to `http://localhost:5180` in Chrome
2. Right-click any element → "Inspect element for agent"
3. Or: Select text → right-click → "Send selection to agent"
4. Or: Click extension popup → "Inspect Element for Agent"

### 4. Check the context file

```bash
cat /opt/workstation/sessions/my-feature/context/latest-ui-context.md
```

Output:
```markdown
# Latest UI Context

**Event type:** inspect
**Timestamp:** 2026-06-03T21:30:00Z
**URL:** http://localhost:5180/

## Element
- **Tag:** `<button>`
- **ID:** `submit-btn`
- **Class:** `btn-primary`

## Source Resolution
- **Framework:** react
- **Component:** `SubmitButton`
- **File:** `src/components/SubmitButton.jsx`
- **Line:** 15
- **Confidence:** high

## Suggested Agent Action
Open `src/components/SubmitButton.jsx` at line 15 and inspect the `SubmitButton` component.
```

### 5. Agent reads the context

The agent (OpenHands or any tool reading the workspace) can:
- Read `latest-ui-context.md` for the most recent UI interaction
- Read `ui-events.jsonl` for full event history
- Use the source file + line number to navigate directly to the code

## Advanced Usage

### Multiple sessions

```bash
glue session create auth-feature --repo /opt/workstation/repos/app
glue session create api-refactor --repo /opt/workstation/repos/app
glue session list
```

### View event history

```bash
# All events
curl -s http://localhost:9876/events | python3 -m json.tool

# Events for specific session
curl -s "http://localhost:9876/events?session_id=my-feature" | python3 -m json.tool
```

### Bridge service status

```bash
glue bridge status
# Bridge service: ok (v0.2.0)
```

## Context Menu Items

| Menu Item | When Available | Action |
|-----------|---------------|--------|
| "Send selection to agent" | Text is selected | Captures selected text + element metadata |
| "Inspect element for agent" | Always (right-click) | Activates crosshair inspector mode |

## Tips

- Source resolution only works on **development builds** (not production minified code)
- The extension only activates on `localhost` and `127.0.0.1` URLs
- If source resolution shows "confidence: low", the framework debug data may not be available
- Use Chrome DevTools → Sources panel to verify source maps are loaded
