# Current sessions architecture

This document describes the current implemented sessions architecture without replacing the scaffolded design documents. Existing scaffold docs remain authoritative for intended direction. This file clarifies what is currently wired, what is scaffolded as design, and how the pieces fit together.

## Architectural center

The new sessions architecture has two related but separate layers:

```text
Session graph layer
  typed session records
  graph edges
  graph events
  context projections
  adapter sessions
  policy evidence
  preview/apply topology planning

Execution session layer
  prompt intake
  advisory planning through agent-core
  workflow handoff
  runtime validation
  executor routing
  live feed events
  action outcomes
```

The graph layer answers: what is this unit of context, how does it relate to other units, and what context may be projected into the active target?

The execution layer answers: what should be done now, is the action allowed in this runtime context, and what happened when it ran?

These layers should interoperate, but they should not collapse into one object.

## Implemented graph model

The graph model is implemented in `control-plane/api/models/session_graph.py`.

A graph session is a `SessionRecord` with:

```text
id
kind
title
summary
status
parent_id
root_id
facets
policy
state
metadata
created_at
updated_at
created_from_event_id
```

The implemented session kinds are:

```text
repo
app
goal
work
question
validation
pull_request
deployment
adapter
runtime
memory
artifact
container
```

A session kind is the coarse identity. Facets carry kind-specific structure. This lets a repo session, goal session, runtime session, and adapter session share a common kernel without forcing all of them into one narrow schema.

## Implemented graph store

`SessionGraphStore` lives in `control-plane/api/services/session_graph_service.py`.

Current storage is JSON-backed by default:

```text
SESSION_GRAPH_PATH if provided
else $SESSIONS_DIR/session-graph.json
else /opt/workstation/sessions/session-graph.json
```

The JSON store is intentional scaffold infrastructure. It supports local tests and early integration. It is not a statement that JSON should remain the production source of truth. Existing docs that describe PostgreSQL, JSONB facets, adjacency tables, locks, artifacts, projections, and vector memory remain valid as target documentation.

Current store behavior includes:

```text
load and validate graph snapshots
atomic save through temp-file replacement
file lock on platforms with fcntl
create sessions
append edges
append events
append projections
apply session update proposals
reject duplicate session ids
reject duplicate edge triples
reject missing edge endpoints
reject self-cycles
reject containment cycles
```

## Session graph API

The session graph router is implemented in `control-plane/api/session_graph.py` under:

```text
/api/session-graph
```

It exposes:

```text
GET  /sessions
POST /sessions
GET  /sessions/{session_id}
GET  /edges
POST /edges
POST /mount/preview
POST /mount
POST /unmount
POST /adapt
PUT  /adapters/{adapter_session_id}/mappings
GET  /events
GET  /context-projection/{session_id}
POST /session-update/apply
GET  /snapshot
```

The API is not generic graph CRUD. Mounting, adapting, unmounting, mapping updates, projection lookup, and proposal application are separate operations because they carry different validation and audit semantics.

The router uses lightweight scope headers:

```text
X-Workspace-Id
X-User-Id
```

These are scaffolding for future auth. They already enforce workspace/private visibility checks in graph and architecture routes.

## Non-destructive session movement

The core invariant is:

```text
Moving a session is not a destructive parent rewrite.
```

When a source session is mounted under a target session, the source keeps its identity, root, events, policy, and facets. The control plane records the relationship using graph records.

A mount may produce:

```text
mounted_under edge
optional adapter session
adapts_from edge
adapts_into edge
adapted_under edge
context projection
policy evidence
warnings
events
```

This is how the system supports unusual but useful operations such as mounting a full repo under a small goal session.

## Adapter engine

The adapter engine is implemented in `control-plane/api/services/session_adapter_engine.py`.

It owns semantic mount execution. It resolves source and target sessions, validates mount policy, creates adapter sessions when needed, creates adapter edges, creates context projections, and returns warnings.

Adapter sessions are created when interpretation is required. This includes cross-kind mounts, ambiguous mount modes, broad source to focused target relationships, or long user intent.

An adapter session contains an adapter facet with:

```text
source_session_id
target_session_id
source_role
target_role
preservation_mode
adaptation_mode
mapping_status
mappings
constraints
non_goals
```

Default mappings are hypotheses. They document a likely semantic relationship, not completed integration.

## Context projections and budget

A context projection describes what source context can flow into the active target.

A projection records:

```text
active_session_id
source_session_ids
projection_mode
projection_source
relevance_score
evidence
include_selectors
exclude_selectors
budget
rationale
```

Current heuristic budgeting is smaller for focused targets and larger for broad targets:

```text
focused target: 4000 tokens, 12 files, 50 events
broader target: 12000 tokens, 40 files, 200 events
```

This is the implementation of the smaller-budget concept: do not let a mounted source dominate the active goal. Project only the context needed for the target.

## Architecture planner and preview/apply API

The architecture planner is implemented in `control-plane/api/services/session_architecture_planner.py`.

It converts topology intent into deterministic `SessionArchitecturePlan` records. It does not persist graph state, allocate worktrees, call `agent-core`, start workflows, or call executors.

The architecture router is implemented in `control-plane/api/session_architecture.py` under:

```text
/api/session-architecture
```

It exposes preview and apply endpoints for:

```text
create root
create child
create sibling
move under
question only
context source preview
```

Preview returns the proposed architecture change. Apply persists it through `SessionGraphStore.apply_update_proposal`.

The current server mounts this router through a bootstrap in `control-plane/api/service_updater.py`. This is compatibility scaffolding around the existing large server module.

## Execution session layer

The execution-oriented session controller is separate from the graph architecture layer.

Key files:

```text
control-plane/sessions/controller.py
control-plane/sessions/models.py
control-plane/sessions/routes.py
control-plane/workflows/execute_agent_plan.py
control-plane/execution/runtime_validator.py
control-plane/adapters/execution/router.py
control-plane/execution/deterministic_executor.py
control-plane/execution/agentic_executor.py
control-plane/agent_core_client/client.py
```

The intended execution flow is:

```text
prompt received
route prompt
request advisory plan from agent-core
validate plan through agent-core
start workflow
execute each plan step
runtime validate each action
route to deterministic, composite, or agentic executor
emit live-feed events
record outcomes back to agent-core
```

Graph topology changes and executor actions should remain separate. A graph mount should not run code. An executor should not silently rewrite graph topology.

## Current safety boundaries

Current runtime hardening includes:

```text
agent-core execution endpoints are deprecated
agent-core plans are advisory only
jubilant-goggles performs runtime validation
high-risk actions require gate evidence
commit is not a default allowed action
path validation resolves paths relative to worktree
apply_patch applies unified diffs instead of writing diff text into files
blocked outcomes are part of the action outcome contract
```

These changes make the platform safer, but they are not the end state. Approval storage, durable locks, workflow state, and graph persistence still need production hardening.

## Relationship to scaffold documentation

Scaffold documentation in this repository is intentional and should be preserved. It describes target architecture, migration direction, and design constraints.

Use this rule when reading docs:

```text
Current architecture docs describe what is wired now.
Scaffold docs describe intended architecture and constraints.
Neither should erase the other.
```

The most important existing scaffold docs are:

```text
docs/session-platform-intent.md
docs/session-graph-control-plane.md
docs/session-adapter-control-plane.md
docs/api-session-graph.md
docs/architecture/session-architecture-planner.md
docs/architecture/session-architecture-preview-api.md
docs/architecture/runtime-adapters-and-execution.md
docs/end-to-end-workflow.md
docs/sql/session_graph.sql
```

## Immediate documentation gaps

The next documentation pass should add cross-links rather than replace scaffold text:

```text
README link to this current architecture document
session graph API examples using real request bodies
architecture API preview/apply examples
adapter mapping lifecycle examples
context projection examples for repo to goal and runtime to repo
graph layer versus execution layer boundary diagram
migration note from JSON scaffold to Postgres store
```
