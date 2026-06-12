# Session platform intent

This document records the control-plane intent for the session graph, SessionAdapter Engine, API routes, persistence scaffold, and UI surfaces.

## Core intent

The control plane should expose the same session semantics as `agent-core`. Repositories, goals, work sessions, app compositions, adapters, runtimes, validation runs, and questions are all graph-addressable sessions.

The control plane is responsible for making these semantics operational. It receives API requests, validates graph mutations, persists sessions and edges, emits events, stores projections, and exposes state to the UI.

## Source identity preservation

Moving or mounting a session must not rewrite the source. A source repo, app, container, or goal keeps its title, kind, parent, root, policy, and history. The control plane records new graph structure around the source instead of destructively changing it.

Mount operations should produce:

- a `mounted_under` edge
- an adapter session when required or requested
- adapter edges
- a context projection
- policy evidence
- warnings
- events

This makes unusual operations safe. A large repo can be mounted under a small goal, but the relationship must be explicit and auditable.

## Adapter intent

The adapter session records interpretation. It explains how source intent maps into target intent without claiming that the source natively belongs to the target.

Default mappings must be neutral unless capabilities are explicitly present on the source session or recovered by inspection. The fallback concepts are:

- session summary
- documented capabilities
- known interfaces
- relevant constraints

The engine should not hard-code vendor-specific behavior into fallback mappings.

## Projection intent

Context projection is the boundary between graph memory and execution context. It decides which source context is relevant to the target and which context should be excluded.

A projection should include:

- active session id
- source session ids
- projection mode
- projection source
- relevance score
- evidence
- include selectors
- exclude selectors
- budget
- rationale

Broad sources mounted under focused targets should receive a narrower budget and explicit exclusions for unrelated UI, deployment, plugin, historical-noise, and unrelated-capability context.

## Policy intent

Policy is validated before graph mutation. The control plane should distinguish source outbound mount permission, target inbound mount permission, source outbound adaptation permission, target inbound adaptation permission, visibility, license constraints, security constraints, and explicit authorization.

Private cross-root projection requires explicit authorization.

Policy evidence should be returned in mount results and persisted through events where useful so downstream execution and UI surfaces can explain why a context transfer was allowed.

## Event intent

Events preserve operation history. The JSON store and future Postgres store may materialize sessions, edges, and projections for reads, but event history remains the audit trail.

During the scaffold phase, event payloads should include created objects when practical:

- `session.created` includes `data.session`
- `session.linked` includes `data.edge`
- `session.mounted` includes `data.edge`
- `session.adapter_created` includes `data.session`
- `session.adapter_projection_created` includes `data.projection`

## API intent

The API should make the architecture explicit rather than hiding everything behind generic CRUD. Mount preview, mount commit, adapt, unmount, mapping update, event listing, projection lookup, and session-update application are distinct operations because they carry different validation and audit semantics.

## UI intent

The UI can make session movement feel simple, but it should not hide policy, adapter, warning, or projection information. Users should be able to inspect what was mounted, why an adapter exists, what was projected, what was excluded, and what policy evidence allowed the operation.

## Persistence intent

The local scaffold uses JSON persistence. The intended production direction is PostgreSQL with JSONB facets, adjacency tables, projection records, adapter mappings, artifacts, locks, and pgvector-backed memory chunks.

Postgres should be the source of truth for sessions, edges, projections, locks, policies, artifacts, and event history. Hatchet can consume events and orchestrate durable work, but it should not replace the graph store.
