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

## Adjacent features scaffolded

### Selection history and replay

`history.js` provides local extension storage helpers for recent browser-region requests. It stores session id, page metadata, region bounds, selected target summaries, prompt text, evidence id, and task id. It deliberately avoids retaining raw visual fallback data in long-term history.

### Source hints

`source-hints.js` extracts optional source information from framework-neutral data attributes and known dev-mode framework metadata. Supported hints include:

```text
data-jg-source-file
data-jg-source-line
data-jg-component
data-source-file
data-source-line
data-testid
data-test
window.__JG_COMPONENT_SOURCE_MAP__
```

React, Vue, and Angular dev-mode hints are treated as opportunistic enrichment, not required dependencies.

### Evidence confidence

`confidence.js` scores selected evidence as low, medium, or high based on source hints, framework hints, stable identifiers, and selectors. Visual-only fallback starts as low confidence.

### Browser-side status feedback

`status.js` scaffolds polling for the active session chat status and a browser toast primitive. This gives the developer feedback after submitting from the page instead of forcing them to switch to the dashboard.

### Prompt templates

`templates.txt` documents first-pass prompt categories for common front-end work: visual polish, responsive fixes, accessibility, copy changes, interaction bugs, component extraction, loading/error states, and matching nearby style.

### Visual fallback policy

`visual-fallback-policy.md` defines when visual fallback evidence is allowed, how it should be marked, and what should not be retained by default.

## Files

```text
manifest.json                 Chrome extension manifest
background.js                 context menu, settings, visible-tab capture, chat submission
page-selector.js              in-page drag selector and edit dialog
overlay.css                   region and dialog styling
settings.html                 extension settings shell
settings.js                   settings persistence
history.js                    local selection history scaffold
source-hints.js               framework/source-hint extraction scaffold
confidence.js                 evidence confidence scoring scaffold
status.js                     browser-side session status scaffold
templates.txt                 prompt template catalog
visual-fallback-policy.md     visual fallback policy
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

## Agent contract

The browser-generated instruction must always include:

```text
user request
page URL/title
region bounds
selected DOM/component targets
source hints when available
framework hints when available
ambient evidence id when available
visual fallback marker when used
```

The executor should resolve source in this order:

1. explicit source hints;
2. data-testid/id/selector search;
3. visible text and route search;
4. framework component name search;
5. visual fallback evidence and region bounds.

## Installation

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Load unpacked extension from `control-plane/extension`.
4. Open extension settings and set the control-plane URL if it is not `http://127.0.0.1:9877`.
5. Navigate to a local app page and use the right-click menu.
