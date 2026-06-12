# UI capability gating intent

## Purpose

The control plane should not use CSS as the durable mechanism for deciding whether a user can see or use a product feature. CSS is the visual layer. Product availability belongs to backend state and typed frontend rendering logic.

This document records the intent behind the UI capability scaffold so future agents do not reintroduce global CSS selectors as feature gates.

## Problem being corrected

The current platform contains `control-plane/web/src/no-placeholder-actions.css`. That file is an explicit quarantine layer for UI controls that are not yet backed by a route, mutation, inspection view, copy action, or external target.

That quarantine is acceptable as a short-term safety net, but it is not the target architecture because it has these failure modes:

- Product logic is hidden in selectors instead of component code.
- Selectors depend on labels and class names that can drift.
- Feature availability is not easy to unit test.
- Unsupported controls still exist in source and are merely suppressed visually.
- Authorization, workflow state, endpoint availability, and service health cannot be represented safely by CSS.

## Target architecture

Use this stack instead:

1. Backend capability contract: `GET /api/ui/capabilities`.
2. Typed frontend helper: `control-plane/web/src/capabilities.tsx`.
3. Component-level rendering through `FeatureGate` or `CapabilityButton`.
4. CSS only for visual state, spacing, layout, theming, and responsive behavior.

The backend route is intentionally static at first. Future revisions can compute capability records from:

- service health
- organization policy
- authenticated user permissions
- workspace settings
- repository state
- installed integrations
- scheduler availability
- remote desktop configuration

The frontend contract should not need to change when those backend sources become dynamic.

## Capability semantics

Each capability has:

- `key`: stable feature identifier, such as `sidebar.review`.
- `label`: user-facing label.
- `area`: product area, such as `sidebar`, `workspace`, `session`, or `session_graph`.
- `enabled`: whether the platform can currently perform the action.
- `visibility`: one of `render`, `disabled`, or `omit`.
- `reason`: why the capability has this state.
- `endpoints`, `routes`, `local_actions`, `external_targets`: concrete backing behavior.
- `intent`: architectural guidance for future implementation.

Use `omit` when a control has no meaningful behavior. Use `disabled` when the behavior exists but is unavailable because of temporary state, permissions, service health, or incomplete user input. Use `render` when the control is actually actionable.

## Migration rule

When removing a selector from `no-placeholder-actions.css`, perform the migration in this order:

1. Add or update a capability record in `control-plane/api/routes/ui_capabilities.py`.
2. Import `useUiCapabilities`, `FeatureGate`, or `CapabilityButton` into the relevant frontend component.
3. Render the control only through the capability contract.
4. Preserve accessibility labels and disabled reasons.
5. Delete the matching quarantine selector from `no-placeholder-actions.css`.
6. Document any newly required endpoint or route.

## Non-goals

This scaffold does not implement authentication, role-based access control, workspace persistence, or a dynamic policy engine. It only creates the stable API and frontend seam required to add those later.

## CSS policy

CSS may control:

- layout
- spacing
- typography
- color
- density
- animations
- responsive behavior
- hover, focus, selected, loading, and disabled visual states

CSS must not control:

- whether a feature exists
- whether a user is allowed to perform an action
- whether an endpoint exists
- whether a route is meaningful
- whether a workflow step can be submitted
- whether an agent action is safe
- whether a service is healthy enough to expose a control

## Current scaffolded files

- `control-plane/api/routes/ui_capabilities.py`
- `control-plane/web/src/capabilities.tsx`
- `control-plane/docs/ui-capability-gating.md`

## Intended endpoint

```http
GET /api/ui/capabilities
```

The response is intentionally simple:

```json
{
  "version": 1,
  "intent": "Use backend capabilities and typed React gates for product behavior...",
  "capabilities": [
    {
      "key": "sidebar.review",
      "label": "Review",
      "area": "sidebar",
      "enabled": false,
      "visibility": "omit",
      "reason": "No review dashboard route or review-action mutation endpoint exists yet.",
      "endpoints": [],
      "routes": [],
      "local_actions": [],
      "external_targets": [],
      "intent": "Review should be visible only after review data and review mutations are implemented."
    }
  ]
}
```

## Example frontend usage

```tsx
const { byKey } = useUiCapabilities()

<FeatureGate capability={byKey['sidebar.review']}>
  <SidebarItem label="Review" />
</FeatureGate>

<CapabilityButton capability={byKey['session.review_actions']} onClick={submitReview}>
  Approve
</CapabilityButton>
```

## Success criterion

A future reader should be able to answer this question from component code and the capability endpoint, not from global CSS:

> Why is this control visible, disabled, or absent?
