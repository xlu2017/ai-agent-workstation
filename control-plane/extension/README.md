# Workstation Component Selector Extension

This Chrome extension scaffolds browser-native front-end edit requests.

## Workflow

1. Open a locally served front-end app in Chrome.
2. Right-click the page.
3. Choose **Select component for agent edit**.
4. Drag to select one or more visible UI components.
5. Confirm the selected region.
6. Enter the requested edit directly in the browser dialog.
7. Press Enter to send the request to the active workstation session.
8. The request is submitted to the normal session chat endpoint.

## Context sent to the session

The extension sends:

- page URL and title;
- region bounds;
- selected DOM targets when identifiable;
- stable selectors when available;
- text, role, id, class, data-testid, and framework hints;
- fallback image evidence only when no DOM target is identified.

## Files

```text
manifest.json       Chrome extension manifest
background.js       context menu, settings, visible-tab capture, chat submission
page-selector.js    in-page drag selector and edit dialog
overlay.css         region and dialog styling
settings.html       extension settings shell
settings.js         settings persistence
```

## Backend integration

The current extension posts to the existing control-plane session chat endpoint:

```text
POST /api/sessions/{session_id}/chat
```

It also attempts to persist ambient context through:

```text
POST /api/sessions/{session_id}/ambient/events
```

If the ambient router is not mounted yet, chat submission still proceeds. Mounting the ambient router makes selected component evidence available in the ambient event log and context packet builder.
