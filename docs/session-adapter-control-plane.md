# Session adapter control-plane behavior

This document describes the expected FastAPI/control-plane behavior for session mounts and adaptations.

## Intent

The control plane turns the session platform intent into API behavior. It must keep session movement explicit, validated, auditable, and reversible.

A user action such as moving one repo session under a goal session should not mutate the source repo. It should create graph records that explain the relationship.

## Preview before commit

`POST /mount/preview` should produce the same structure as `POST /mount` without persisting it. This lets the UI show warnings, policy evidence, projected context, adapter mappings, and graph changes before commit.

Preview output should be deterministic for the same graph and request.

## Mount commit

`POST /mount` should:

1. resolve source and target sessions
2. reject missing sessions
3. reject self-mounts
4. validate policy
5. require adapter sessions for cross-kind, ambiguous, or non-trivial mounts
6. create a mounted edge
7. create an adapter session when requested or required
8. create adapter edges
9. create a context projection
10. append events
11. validate the candidate graph
12. persist the candidate graph

## Adapt commit

`POST /adapt` creates an adapter session without necessarily creating a mounted edge. It is useful when a user wants semantic mapping before contextual placement.

The operation should still validate policy and graph integrity.

## Unmount

Unmounting should remove the mounted relationship, not delete the source. Optional adapter cleanup should be explicit. The operation should append an event explaining why the relationship changed.

## Mapping updates

Adapter mappings are hypotheses until validated by inspection, tests, or user confirmation. Mapping updates should preserve evidence and status.

The API should support both replacement and append modes so users can refine mappings without losing history unintentionally.

## Policy evidence

Mount and adaptation responses should expose policy evidence. This is not only for debugging. It is part of the trust boundary between graph context and execution.

## UI obligations

The UI should expose:

- source session
- target session
- adapter session
- warnings
- policy evidence
- projected context
- excluded selectors
- mapping status
- event history

The user should be able to understand why a mount was allowed and what context will flow into execution.

## Persistence obligations

The JSON store is a scaffold. The Postgres implementation should preserve the same records and constraints:

- sessions
- session_edges
- session_events
- session_context_projections
- session_adapter_mappings
- session_artifacts
- session_locks
- session_memory_chunks

The database should enforce uniqueness where possible, especially session ids, edge ids, and duplicate edge triples.
