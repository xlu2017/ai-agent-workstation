# Execution Activation Bridge

## Intent

Graph chat can already create a work session under an existing goal session. That is only a task record. It is not proof that code execution has started.

The next architecture boundary is a shared execution activation service used by every entry point that wants to start work:

```text
ready work session
-> request agent-core recommend-next
-> validate the action contract
-> validate platform/runtime permissions
-> start the workflow adapter
-> emit truthful events
```

## Current problem

`SessionController._request_next_action_and_start_workflow` owns the working path for `/api/v2/sessions`, but graph chat creates `SessionKind.WORK` nodes without entering that path. The result is a truthful but incomplete state: the user sees an acknowledgement and a work session, while no workflow has started.

## Source of truth

The shared activation service should become the only place that can turn a pending work unit into running execution. It should be called from:

```text
/api/v2/sessions/{id}/prompts
/api/session-graph/sessions/{id}/chat
repository attachment updates
manual start controls
```

## Non-goals for the scaffold

This scaffold must not pretend execution worked. Until the extracted service actually starts the workflow adapter, callers must keep:

```text
auto_started = false
execution_state = ready_for_execution | blocked_needs_repo
```

Only a successful workflow adapter response may set:

```text
auto_started = true
execution_state = started
```

## Required implementation phases

### Phase 1: Extract shared activation

Move the recommend-next and workflow-start body from `SessionController._request_next_action_and_start_workflow` into a service that accepts a canonical activation request.

### Phase 2: Wire classic sessions to the service

Keep `/api/v2/sessions/{id}/prompts` behavior unchanged, but call the shared service instead of the private controller method.

### Phase 3: Wire graph chat to the service

When graph chat creates a ready work session, build an activation request from the work node and parent goal. If the repo is missing, keep the work blocked. If the repo exists, call the activation service.

### Phase 4: Add repo attachment trigger

When a goal gains `repo_session_id`, find blocked child work sessions and transition them to `ready_for_execution`. Then call the same activation service.

### Phase 5: Prove no fake success

Tests must assert that no endpoint reports `auto_started = true` unless the workflow adapter accepted a plan.

## Acceptance tests

```text
repo attached + graph chat follow-up
  emits work.started
  emits plan_requested, plan_generated, plan_started after activation
  returns auto_started true only after workflow start succeeds

no repo + graph chat follow-up
  creates blocked work session
  does not request a plan
  does not start workflow

repo attached after blocked work exists
  marks blocked work ready
  calls activation service
  still does not claim started if activation is not configured

agent-core unavailable
  emits planning failure
  does not start workflow
  returns user-visible planning failure

no fake execution
  commit_created never appears unless a real commit action succeeded
```

## Event contract

The bridge should use existing event names where possible:

```text
user.interjected
work.started
plan_requested
plan_generated
plan_started
action_started
action_completed
action_failed
action_blocked
plan_completed
```

The graph event stream can use graph event names for graph-local transitions, but execution telemetry should converge on the live feed event vocabulary.
