# RFC-002: Source-Aware UI Selection

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Enable users to click on any UI element in a running web application and instantly resolve it to the exact source code file, line number, and component — then pass that context to an AI agent for modification.

## Motivation

Current agent workflows require the user to describe UI elements in text ("the button on the checkout page"). This is:
- Ambiguous (which button?)
- Slow (agent must search the codebase)
- Error-prone (agent may modify the wrong component)

Direct UI-to-source resolution eliminates this friction.

## Architecture

See `ui-bridge-service/ARCHITECTURE.md` for the full pipeline.

### Phase 1 (Implemented — Scaffolding)
- Chrome extension captures element metadata
- React `_debugSource` resolution
- Bridge service stub

### Phase 2 (This RFC)
- Source map parsing for production builds
- Vite HMR module graph integration
- Next.js turbopack source map API
- CDP integration for coverage-based resolution

### Phase 3 (Future)
- Vue.js support
- Svelte support
- CSS-to-source resolution
- Visual diff generation

## Source Map Resolution

### Vite Dev Server
```
GET /@fs/src/components/Button.tsx → raw source
GET /src/components/Button.tsx?t=123 → transformed source + inline map
```

The bridge service can:
1. Intercept source map URLs from Chrome DevTools Protocol
2. Parse `.map` files to get original → generated mappings
3. Reverse-map from DOM element position to source position

### Next.js
```
GET /_next/static/chunks/app/page-abc123.js.map
```

Source maps embed `"sources": ["webpack:///src/components/Button.tsx"]` which maps back to the original file.

### React DevTools Integration

React DevTools exposes `__REACT_DEVTOOLS_GLOBAL_HOOK__` which provides:
- Component tree with file locations
- Props and state
- Update tracking

The bridge can hook into this for richer context than `_debugSource` alone.

## Agent Context Generation

```json
{
  "instruction": "Change the button color to blue",
  "target": {
    "file": "src/components/CheckoutButton.tsx",
    "line": 23,
    "component": "CheckoutButton",
    "parent": "CheckoutForm",
    "props": {"variant": "primary", "disabled": false}
  },
  "surrounding_code": "...",
  "related_files": ["src/styles/buttons.css"]
}
```

## Security

- Only works on localhost (development servers)
- No source maps served in production
- Extension requires explicit user activation per page

## Open Questions

1. How to handle CSS Modules / Tailwind (class names are transformed)?
2. Server Components in Next.js (no client-side fiber)?
3. Performance impact of source map loading?
