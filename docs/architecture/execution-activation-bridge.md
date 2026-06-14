# Execution Readiness Bridge

## Intent

Graph chat can already create a work session under an existing goal session. That is only a task record. It is not proof that code execution has started.

The next architecture boundary is a shared execution readiness service used by every entry point that wants to prepare work for execution:

```text
ready work session
-> request agent-core recommend-next
-> validate the first action contract
-> validate platform/runtime permissions
-> mark executor start as pending
-> emit truthful events
```

## Current problem

`SessionController._request_next_action_and_start_workflow` owns the working path for `/api/v2/sessions`, but graph chat creates `SessionKind.WORK` nodes without entering that path. The result is a truthful but incomplete state: the user sees an acknowledgement and a work session, while no executor has started.

## Source of truth

The shared execution readiness service should become the only place that can turn a pending work unit into either:

```text
blocked_needs_repo
ready_not_started
started
failed
```

It should be called from:

```text
/api/v2/sessions/{id}/prompts
/api/session-graph/sessions/{id}/chat
repository attachment updates
manual start controls
```

## Non-goals for the scaffold

This scaffold must not pretend execution worked. Until the extracted service actually starts the executor adapter, callers must keep:

```text
auto_started = false
execution_state = ready_for_execution | blocked_needs_repo
```

Only a successful executor adapter response may set:

```text
auto_started = true
execution_state = started
```

## Public response vocabulary

Graph chat should return:

```text
execution_readiness
initial_execution_scaffold
executor
executor_start
```

It should not expose old activation terms in frontend-facing response payloads.

## Required implementation phases

### Phase 1: Extract shared execution readiness

Move the recommend-next and executor-start body from `SessionController._request_next_action_and_start_workflow` into a service that accepts a canonical execution readiness request.

### Phase 2: Wire classic sessions to the service

Keep `/api/v2/sessions/{id}/prompts` behavior unchanged, but call the shared service instead of the private controller method.

### Phase 3: Wire graph chat to the service

When graph chat creates a ready work session, build an execution readiness request from the work node and parent goal. If the repo is missing, keep the work blocked. If the repo exists, record execution readiness and return the initial execution scaffold.

### Phase 4: Add repo attachment trigger

When a goal gains `repo_session_id`, find blocked child work sessions and transition them to `ready_for_execution`. Then call the same execution readiness service.

### Phase 5: Prove no fake success

Tests must assert that no endpoint reports `auto_started = true` unless the executor adapter accepted a start request.

## Acceptance tests

```text
repo attached + graph chat follow-up
  emits work.execution_readiness_recorded while executor start is pending
  returns initial_execution_scaffold with exactly one first read/search action
  returns auto_started true only after executor start succeeds

no repo + graph chat follow-up
  creates blocked work session
  does not return a first action scaffold
  does not start executor

repo attached after blocked work exists
  marks blocked work ready
  records execution readiness
  still does not claim started if executor start is not configured

agent-core unavailable
  returns prompt_routing_unavailable
  does not mutate the graph
  does not start executor

no fake execution
  commit_created never appears unless a real commit action succeeded
```

## Event contract

Graph-local readiness events should use graph event names:

```text
user.interjected
work.execution_readiness_recorded
work.started
```

Execution telemetry should converge on the live feed event vocabulary only after the executor actually starts:

```text
action_started
action_completed
action_failed
action_blocked
plan_completed
```
