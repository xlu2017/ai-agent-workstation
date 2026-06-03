# RFC-004: Flutter Bridge

**Status:** Draft
**Author:** Infrastructure Team
**Created:** 2026-06-03

## Summary

Extend the UI-to-Code bridge to support Flutter applications via the Dart VM Observatory and Widget Inspector.

## Motivation

Flutter uses a completely different rendering model (Skia canvas, not native views or DOM). Resolution requires Flutter-specific tooling.

## Architecture

```
┌──────────────────┐
│  Flutter App     │
│  (debug mode)    │
└────────┬─────────┘
         │ Dart VM Service Protocol (ws://localhost:XXXX)
         │
┌────────┴─────────────┐
│  Flutter Bridge Svc  │  :9878
│  (extends ui-bridge) │
└────────┬─────────────┘
         │
┌────────┴─────────────┐
│  Widget Inspector    │
│  (via VM service)    │
└──────────────────────┘
```

## Key Technologies

### Dart VM Service Protocol
- WebSocket-based protocol for debugging
- Provides widget tree inspection
- Source location data in widget `creationLocation`

### Widget Inspector
- `ext.flutter.inspector` service extension
- Returns widget tree with `creationLocation`:
  ```json
  {
    "file": "file:///path/to/lib/src/button.dart",
    "line": 42,
    "column": 10
  }
  ```

### Flutter DevTools
- `dart devtools` provides web-based inspector
- Can be automated for element selection

## Resolution Method

1. Connect to VM service WebSocket
2. Call `ext.flutter.inspector.getSelectedWidget`
3. Extract `creationLocation` from widget
4. Map to source file and line number

## Implementation Plan

1. Parse VM service URI from Flutter debug output
2. Implement WebSocket client for Dart VM protocol
3. Query widget tree on user selection
4. Extract and return source location

## Prerequisites

- Flutter SDK installed
- App running in debug mode
- VM service port accessible

## Open Questions

1. How to trigger "select widget" from external tool?
2. Release mode has no widget inspector — document limitation?
3. Web (Flutter Web) vs mobile (Dart native) differences?
