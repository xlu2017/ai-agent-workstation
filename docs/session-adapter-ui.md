# Session adapter UI

The dashboard includes an implemented Session Graph page at `/session-graph`.

## Intent

The UI is the operator surface for the session architecture. It should make graph semantics visible instead of hiding them behind generic CRUD. A user should be able to see what is a source, what is a target, what was mounted, why an adapter exists, what context is projected, and what policy checks allowed or blocked a change.

## Current capabilities

The page now supports:

- loading `GET /api/session-graph/snapshot`
- graph summary counters for sessions, edges, projections, adapters, mounts, and events
- search by title, summary, or id
- session kind filtering
- grouped graph canvas by session kind
- clickable session nodes
- clickable relationship chips
- selected session details with policy, facets, edge count, and recent events
- selected edge details with metadata
- mounted source panel with unmount action
- adapter detail panel with mapping, role, preservation, adaptation, constraint, and non-goal visibility
- context projection panel with source/active scope, projection source, relevance, budget, selectors, and evidence
- recent event panel
- mount preview form backed by `POST /api/session-graph/mount/preview`
- mount apply action backed by `POST /api/session-graph/mount`
- unmount action backed by `POST /api/session-graph/unmount`

## Mount preview flow

1. User selects a source session.
2. User selects a target session.
3. User enters mount intent.
4. User selects mount mode and adapter options.
5. UI calls preview endpoint.
6. UI displays warnings, policy checks, adapter session, edge changes, and projection budget.
7. User applies the mount only after reviewing the preview.

## Design constraints

- Preview must not persist graph changes.
- Apply must go through the API so policy and graph validation remain server-owned.
- Unmount must remove the relationship, not the source session.
- The UI should display adapter and projection evidence rather than only showing names.
- Source identity must remain visible after mount and adaptation.

## Later work

- Replace the grouped CSS canvas with React Flow or another explicit graph renderer.
- Add adapter mapping confirmation and rejection controls.
- Add session creation and typed facet editing forms.
- Add active-session switch controls once locking and policy are finalized.
- Add optimistic refresh and toast notifications.
- Add route-level UI tests for preview, apply, unmount, selection, filtering, and projection display.
