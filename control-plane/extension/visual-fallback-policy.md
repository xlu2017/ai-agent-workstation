# Visual Fallback Policy

## Purpose

Visual fallback evidence exists for the case where a developer explicitly selects a browser region but the extension cannot map that region to useful DOM or framework targets.

It is not a periodic screen capture system.

## Allowed trigger

```text
right click
  -> choose component selector
  -> drag region
  -> confirm region
  -> no DOM target found
  -> capture visible tab with region bounds
```

## Evidence semantics

Visual fallback evidence is low-confidence supporting evidence. It should be marked as fallback and paired with exact region bounds, viewport size, device pixel ratio, page URL, and page title.

## Retention rule

The extension history should not store raw image data by default. It may store:

```text
fallback was used
region bounds
viewport metadata
ambient evidence id
created timestamp
```

The control plane may store a redacted artifact later, but that requires a dedicated artifact-retention policy.

## Redaction roadmap

Future implementation should redact likely sensitive fields before persistence:

```text
password fields
payment fields
email/token-like text
visible secrets in code panes
private browser tabs outside the workstation scope
```

## Agent guidance

When visual fallback evidence is present, the generated session instruction must say:

```text
No identifiable DOM/component target was selected. Use the visual fallback evidence and region bounds to locate the intended UI area.
```

The agent should still try structured lookup first using URL, nearby text, route, and repository search.
