# RFC-003: React Native Bridge

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Extend the UI-to-Code bridge to support React Native applications, enabling element selection from a mobile simulator/emulator with source resolution.

## Motivation

React Native apps have a different rendering pipeline (native views instead of DOM). The current browser-based approach doesn't work. We need:
- Connection to React Native DevTools
- Element inspector integration
- Source resolution via Metro bundler source maps

## Architecture

```
┌───────────────────┐     ┌──────────────────┐
│  Android Emulator │     │  iOS Simulator   │
│  (or device)      │     │  (macOS only)    │
└────────┬──────────┘     └────────┬─────────┘
         │ React Native DevTools Protocol      │
         └──────────────┬──────────────────────┘
                        │
              ┌─────────┴──────────┐
              │  RN Bridge Service │  :9877
              │  (extends ui-bridge)│
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │  Metro Bundler     │  Source maps
              │  :8081             │
              └────────────────────┘
```

## Key Differences from Web Bridge

| Aspect | Web | React Native |
|--------|-----|-------------|
| Renderer | DOM | Native Views |
| Inspector | Chrome DevTools | RN DevTools / Flipper |
| Source Maps | Webpack/Vite `.map` | Metro bundler |
| Element ID | CSS selector/XPath | testID / nativeID |
| Debug Source | `_debugSource` on fiber | Same (React fiber) |

## Metro Source Map Access

```
GET http://localhost:8081/index.bundle?platform=android&dev=true&sourcemap=true
```

Returns the full source map for the bundle. The bridge service parses this to resolve component names to file locations.

## Implementation Plan

1. Use existing React fiber inspection (`_debugSource` works in RN too)
2. Connect to Metro for source maps
3. Integrate with Android emulator via ADB for element selection
4. Extend UI-bridge service with RN-specific endpoints

## Prerequisites

- Android SDK + emulator (see RFC-005)
- Metro bundler running
- React Native DevTools connection

## Open Questions

1. iOS support requires macOS — handle as remote connection only?
2. Expo vs bare React Native — different Metro configs?
3. Hermes engine debugging support?
