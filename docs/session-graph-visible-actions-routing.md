# Session graph visible-action routing

Graph-session chat routing is a workflow-phase decision, not a task-type inference problem.

When a user sends a follow-up message to:

```text
POST /api/session-graph/sessions/{session_id}/chat
```

jubilant-goggles knows the phase: prompt routing inside an existing graph session. The platform must therefore constrain agent-core recommend-next to the route action only:

```json
["session.route_prompt"]
```

The user prompt supplies intent text. It does not determine the visible action set.

## Request shape

The control plane sends a constrained recommend-next request:

```json
{
  "task_type": "unknown",
  "current_action": "session.route_prompt",
  "completed_actions": [],
  "visible_actions": ["session.route_prompt"],
  "context": {
    "decision_phase": "graph_session_prompt_routing",
    "prompt_kind": "graph_session_followup",
    "visible_actions": ["session.route_prompt"],
    "session_id": "...",
    "target_session_id": "...",
    "prompt": "...",
    "has_repo_context": true
  }
}
```

`task_type` may be `unknown`; it is not used to unlock the routing action.

## Apply result

agent-core recommends `session.route_prompt` with one route:

- `continue_active`: create or continue a work session under the active goal.
- `question_only`: record the message without creating work.
- `create_child_goal`: create a sub-goal under the current graph context.
- `create_sibling_goal`: create a separate root/sibling goal.

Only after this routing pass should the platform expose broader actions such as `session.mount`, `apply_patch`, `run_tests`, or `create_pr`.
