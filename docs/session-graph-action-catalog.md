# Session graph action catalog

The session graph exposes canonical graph-owned actions under `/api/session-graph/actions`. These actions are discoverable by UI and planners, but they are applied by the session graph service layer rather than by the coding/runtime executor.

## Why this exists

Session operations such as mounting one session under another are durable graph changes. They should not be represented as shell commands or coding-agent tools. A planner may recommend them, but execution must remain inside the graph service so policy, visibility, projections, adapter sessions, and audit events remain consistent.

## Endpoints

```text
GET  /api/session-graph/actions
GET  /api/session-graph/actions/{action_name}
POST /api/session-graph/actions/validate
POST /api/session-graph/actions/apply
```

`/actions/apply` is intentionally scoped to graph actions. It does not run shell commands, mutate files, create commits, push branches, deploy, or call the coding executor.

## Initial actions

| Action | Purpose | Backing service |
| --- | --- | --- |
| `session.mount` | Persist a `mounted_under` relationship, optional adapter session, context projection, and audit events. | `session_graph.mount_session` |
| `session.mount.preview` | Validate and preview a mount without persisting graph changes. | `session_graph.preview_mount_session` |
| `session.adapt` | Create an adapter session/projection scaffold between source and target sessions. | `session_graph.adapt_session` |
| `session.unmount` | Remove a persisted `mounted_under` relationship, optionally removing related adapter edges. | `session_graph.unmount_session` |

## Mount parameters

`session.mount` and `session.mount.preview` use the existing `MountSessionRequest` schema:

```json
{
  "source_session_id": "repo-session",
  "target_session_id": "goal-session",
  "user_intent": "Use repo context to implement the goal.",
  "mount_mode": "reference",
  "create_adaptation_session": true,
  "make_active": false
}
```

The catalog action preserves the source session identity. It creates graph relationships and projections instead of copying one session into another.

## Planner contract

A planner may propose `session.mount` when a repo, runtime, app, memory, validation, or artifact session must become available to a goal or work session. The platform must still validate visibility and graph policy before applying the action.

The action catalog is local and authoritative for graph-owned actions. `agent-core` may advise which action to use, but `jubilant-goggles` performs validation and application.
