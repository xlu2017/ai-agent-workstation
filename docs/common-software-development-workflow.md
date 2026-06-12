# Common software development workflow

This platform should represent a normal coding task as session graph topology before action execution. A user may start a session without selecting a repo. Repo scope becomes mandatory only when the task needs repo-dependent execution.

## Walkthrough

1. **Goal or question session** — durable identity for the user request, such as a question, feature, bug fix, refactor, review, architecture change, or integration. This may start unscoped.
2. **Repo session, when needed** — durable identity for the codebase. Store path, branch hints, known commands, ownership, capabilities, and source metadata in repo facets. Pure question and planning sessions may omit this.
3. **Mount and adapter session** — mount the repo under the goal before code execution. Create an adapter when repo context needs translation, filtering, or capability mapping before it is projected into the goal.
4. **Work session** — represent the implementation attempt. Plans, user interjections, tool calls, file changes, and status changes attach to this work session.
5. **Runtime session** — represent server, browser, terminal, emulator, container, or worktree state only when an action needs it. Runtime is not the task identity.
6. **Validation session** — represent test, lint, typecheck, smoke, screenshot, and manual review evidence.
7. **Pull request or artifact session** — represent reviewable output, a patch, deployment, release note, summary, or other handoff artifact.

## Repo requirement rule

```text
Session start: repo optional
Question/planning: repo optional
Implementation/file edit/test/runtime/PR: repo required before execution
```

Do not block creation of an unscoped goal or question session. Instead, block or redirect the first repo-dependent execution action until the user selects or mounts a repo session.

## Recommended graph relationships

```text
repo --mounted_under--> goal
work --implements--> goal
runtime --component_of--> work
validation --validates--> work
work --produces--> pull_request or artifact
```

## What is not a session

A single command, log line, file edit, screenshot, temporary UI state, or tool call should not become its own session by default. Attach it to the nearest durable graph session as an event, facet, projection, or artifact.

## API surface

The compact workflow template is available at:

```text
GET /api/session-graph/workflow/dev
```

The canonical graph schema options are available at:

```text
GET /api/session-graph/options
```

Legacy `/api/sessions` and `/api/v2/sessions` objects remain deprecated without migration.
