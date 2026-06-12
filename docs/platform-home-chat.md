# Platform homepage chat

The platform homepage is graph-native. It starts sessions through `/api/session-graph/sessions` instead of the deprecated `/api/sessions` runtime-session API.

## User flow

1. The user opens `/`.
2. The homepage shows a large centered rectangular chat dialog.
3. The user may leave repository scope unset, select a GitHub repository, or enter/select a local server folder.
4. Pressing Enter in the initial prompt creates a `goal` graph session.
5. If a repository was selected, the homepage also creates a `repo` graph session and applies `session.mount` to mount it under the goal session.
6. The browser navigates to `/session/{goal_session_id}`.

## Repository selection

GitHub repositories are loaded from:

```text
GET /api/repo-provider/repositories
```

That endpoint uses the selected server-side repo provider credential. It never returns tokens to the browser.

Local folders are selected through the existing safe filesystem browser:

```text
GET /api/browse?path=/opt/workstation/repos
```

## Session scope rule

A repository is optional at session start. Repo scope is required only before repo-dependent execution such as file edits, test runs, runtime worktrees, or PR output.

The homepage therefore supports both:

```text
prompt -> goal session
prompt + repo -> repo session + goal session + mounted_under edge
```
