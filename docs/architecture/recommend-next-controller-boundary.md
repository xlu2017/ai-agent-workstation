# Recommend-Next Controller Boundary

## Intent

`recommend-next` is the canonical service for interpreting what should happen
after any user-entered session text.

This document defines the controller boundary for that interpretation step. At
this stage, the service or controller should output only the top-level decision
type returned by recommend-next:

```text
execute
find_out_more
ask_user
stop
```

The controller must not expose or rely on granular platform actions as the first
interpretation result. More specific behavior is selected only after this
controller step.

## Canonical input points

The boundary applies to:

```text
new chat started
existing session chat message
follow-up while work is running
question-like message
control-like message
separate-task request
repo-missing state
```

Every one of those inputs should pass through the same recommend-next
interpretation boundary.

## Decision-type responsibility

### execute

`execute` means the platform should perform a concrete platform operation after
this boundary.

Examples that fall under `execute` after the top-level decision is known:

```text
create a root session
create a child session
create a sibling session
route to an existing session
create a work session
start one executor action
request a commit checkpoint
```

The controller must decide the granular platform operation after it receives the
`execute` decision type. recommend-next should not have to return separate
first-class controller decisions such as `continue_active`,
`create_child_goal`, or `create_sibling_goal` at this level.

### find_out_more

`find_out_more` means the next platform operation should be read-only or low
risk.

Examples that may be selected after this boundary:

```text
read session state
inspect current repo metadata
search recent events
retrieve context
read a file
run a safe status command
```

### ask_user

`ask_user` means no execution should be started until the user answers the
question.

The controller may render an assistant question or clarification prompt. It
must not create fake work or mark execution as started.

### stop

`stop` means the platform should not start more work for the current input.

Missing repo context belongs here at the controller boundary. The platform may
render a message such as:

```text
Attach a repository to start execution.
```

but it should not treat repo attachment as a separate recommend-next decision
type. The later repo-attachment flow may call recommend-next again when the
required context exists.

## Non-goals

This boundary must not:

```text
replace runtime validation
execute actions inside agent-core
authorize filesystem or command operations
perform commits, pushes, deploys, or PR creation
reintroduce local heuristic routers as final authority
require /actions/plan for execution
```

## Future implementation shape

The intended implementation seam is:

```text
User-entered text
  -> append/create durable session state
  -> RecommendNextExecutionService.interpret_user_message(...)
  -> normalize to execute | find_out_more | ask_user | stop
  -> controller dispatches granular platform behavior
  -> runtime validator authorizes concrete action
  -> workflow/executor runs at most one concrete action
  -> outcome is recorded
  -> recommend-next is called again if another decision is needed
```

The existing one-step plan wrapper may remain temporarily as an executor
compatibility envelope, but it must not become the source of next-action
selection.

## Scaffolding status

`control-plane/execution/recommend_next_execution_service.py` is scaffold-only.
It documents the boundary and deliberately raises `NotImplementedError` to avoid
changing runtime behavior before the controller integration is implemented.
