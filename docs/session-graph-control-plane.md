# Session graph control plane

The control plane now has a scaffolded session graph API for treating repos,
apps, goals, work items, validations, pull requests, deployments, adapters, and
containers as one graph of sessions.

## Persistence

The scaffold uses a JSON-backed `SessionGraphStore` by default so local API tests
can run without a database. The intended source of truth is PostgreSQL with JSONB
facets and adjacency tables. Set `SESSION_GRAPH_PATH` to control the local JSON
file path. The Postgres-first SQL shape is documented in
`docs/sql/session_graph.sql`.

Tables covered by the SQL scaffold:

- `sessions`
- `session_edges`
- `session_events`
- `session_artifacts`
- `session_locks`
- `session_context_projections`
- `session_adapter_mappings`
- `session_memory_chunks`

`session_memory_chunks` is written for pgvector so memory embeddings can live in
Postgres beside session events, docs, summaries, and adapter mappings.

## Services

- `SessionGraphStore`: load/save/list/create graph records.
- `preview_mount_session`: returns mount effects without persistence.
- `mount_session`: validates, applies, persists edges/events/projections.
- `create_adaptation_session`: builds adapter session records.
- `generate_default_mappings`: seeds capability mappings.
- `generate_context_projection`: creates focused context budgets.
- `validate_mount_request`: enforces mount/adapt invariants.
- `SessionWorkflowDispatcher`: optional durable-workflow handoff stub.

## Preservation rule

Applying a mount adds edges, events, an optional adapter session, and a context
projection. It does not mutate the source session.

## Workflow boundary

Hatchet can run durable tasks, retries, cancellations, workers, and replay later.
It should not become the canonical session graph store. Canonical graph state
belongs in Postgres; workflow state belongs in Hatchet.
