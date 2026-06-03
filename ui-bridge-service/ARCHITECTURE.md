# UI-to-Code Bridge — Architecture Notes

## Goal

Selected UI element → source map → component → file → line number → agent context

## Resolution Pipeline

```
┌─────────────────────┐
│  Browser Extension   │  User selects element
│  (content.js)        │  Captures: tag, classes, React fiber, XPath
└──────────┬──────────┘
           │ chrome.runtime.sendMessage
           ▼
┌─────────────────────┐
│  Background Worker   │  Routes to bridge service
│  (background.js)     │
└──────────┬──────────┘
           │ HTTP POST /api/resolve
           ▼
┌─────────────────────┐
│  Bridge Service      │  Source map resolution
│  (server.py:9876)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Resolution Result   │  { file, line, column, component }
│  → Agent Context     │  → OpenHands task context
└─────────────────────┘
```

## Framework-Specific Resolution Methods

### React (current — Phase 1)

1. **`_debugSource`** — Available in development builds. React attaches source file/line
   info directly to fiber nodes. Highest confidence (0.95).
2. **Component name grep** — If `_debugSource` unavailable, use component name to
   `rg -n "function ComponentName"` or `rg -n "const ComponentName"` in source.

### Next.js (planned — Phase 2)

1. **Source maps via `/_next/static/`** — Parse `.map` files from dev server.
2. **Next.js Turbopack API** — Query internal source map endpoints.
3. **File conventions** — `app/page.tsx` maps to route `/`, `app/about/page.tsx` → `/about`.

### Vite (planned — Phase 2)

1. **`/@vite/client` source maps** — Vite exposes source maps in dev mode.
2. **Module graph API** — `/__vite_ping` and HMR module graph.
3. **`import.meta.hot`** — Track which module owns which DOM nodes.

### Vue (planned — Phase 3)

1. **Vue Devtools hooks** — `__VUE_DEVTOOLS_GLOBAL_HOOK__`
2. **`__vue_app__` instance** — Access component tree.
3. **SFC source maps** — `.vue` file source maps.

## Chrome DevTools Protocol Integration

Future phases will use CDP for:
- **`Debugger.getScriptSource`** — Get source of loaded scripts
- **`DOM.getNodeForLocation`** — Map coordinates to DOM nodes
- **`CSS.getMatchedStylesForNode`** — Find CSS source
- **`Profiler.getBestEffortCoverage`** — Identify executed source

Connect via: `chrome --remote-debugging-port=9222`

## Data Flow for Agent Context

```json
{
  "element": {
    "tag": "button",
    "classes": ["btn-primary"],
    "text": "Submit",
    "react_component": "SubmitButton"
  },
  "source": {
    "file": "src/components/SubmitButton.tsx",
    "line": 42,
    "column": 5,
    "confidence": 0.95
  },
  "context": {
    "surrounding_code": "...",
    "imports": ["..."],
    "parent_component": "CheckoutForm"
  }
}
```

This context object gets injected into the agent's task description,
allowing it to modify the exact component without searching.

## Security Considerations

- Bridge service only listens on localhost
- Extension only activates on localhost URLs
- No external network calls
- Source maps are only accessible in development mode
