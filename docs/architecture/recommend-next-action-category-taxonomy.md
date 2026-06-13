# Recommend-Next Action Category Taxonomy

## Intent

Every known platform-visible action name must belong to exactly one of the four
recommend-next decision categories:

```text
execute
find_out_more
ask_user
stop
```

This keeps the controller boundary clean. The first interpretation step answers
only the type-level question:

```text
Should the platform execute, find out more, ask the user, or stop?
```

After that, jubilant-goggles may choose a granular platform operation.

The scaffold catalog lives in:

```text
control-plane/execution/recommend_next_action_taxonomy.py
```

## Category rules

### execute

Use `execute` for actions that mutate platform state, mutate repo/worktree state,
create or route sessions, apply controls, or intentionally perform a concrete
user-requested platform operation.

Known examples:

```text
append_to_current
modify_current_plan
interrupt_current
spawn_child_session
spawn_new_session
queue
continue_active
create_child_goal
create_sibling_goal
classify_task
identify_relevant_tests
apply_patch
run_tests
request_approval
commit
commit_checkpoint
autonomous_code_edit
repair_test_failure
browser_debug_loop
multi_file_refactor_loop
investigate_and_patch
open_terminal
open_browser
open_file_manager
take_screenshot
pause
resume
continue
cancel
new_session
parallel
```

Important rule:

```text
creating or routing a session is execute
```

The first decision is still only `execute`; the controller later decides whether
that means creating a root session, child session, sibling session, work session,
or routing to an existing session.

### find_out_more

Use `find_out_more` for read-only or low-risk discovery actions.

Known examples:

```text
retrieve_context
search_memory
grep
read_file
list_files
summarize_diff
inspect_repo_metadata
search_recent_events
run_safe_status_command
```

This category must not imply authorization. Runtime validation still checks
path, command, session, worktree, and permission constraints before anything
runs.

### ask_user

Use `ask_user` when the platform needs user input before it can proceed.

Known examples:

```text
ask_user
request_missing_information
clarify_goal
clarify_repo
clarify_approval
```

No workflow should start for an `ask_user` decision. The platform should render a
question or clarification prompt and wait.

### stop

Use `stop` when the platform should not start more work for the current input.

Known examples:

```text
stop
question_only
blocked_needs_repo
missing_repo_context
blocked_needs_user
blocked_by_policy
unsafe_to_continue
goal_satisfied
```

Important rule:

```text
missing repo context is stop
```

The platform may display a message asking the user to attach a repository, but
repo absence should not become its own controller decision type. When repo
context later exists, the repo-attachment flow may call recommend-next again.

## Unknown action rule

Unknown action names must fail closed.

Future implementation should enforce:

```text
if action_name not in ACTION_DECISION_TYPE_BY_NAME:
  reject or mark invalid until explicitly categorized
```

Do not silently default unknown actions to `execute`.

## Why this exists

Older code paths exposed granular controller decisions directly, including:

```text
continue_active
question_only
create_child_goal
create_sibling_goal
append_to_current
modify_current_plan
spawn_child_session
spawn_new_session
```

Those names are still useful as internal dispatch targets, but they should not
be the first output of the recommend-next controller boundary.

The type-level boundary is:

```text
recommend-next -> execute | find_out_more | ask_user | stop
```

The granular dispatch boundary is later:

```text
execute -> create work session | route session | start one action | apply control | etc.
find_out_more -> read context | inspect repo | search events | etc.
ask_user -> render question
stop -> render status and do not start work
```

## Scaffolding status

This taxonomy is documentation and scaffold only. It does not yet change runtime
behavior, replace existing routers, start workflows, or validate live
recommendations.
