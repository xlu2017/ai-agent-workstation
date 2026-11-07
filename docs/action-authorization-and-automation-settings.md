# Action Authorization and Automation Settings

## Intent

Session chat should not ask the user to approve every obvious action when the user has explicitly enabled automation. The platform still needs hard gates for safety, validation, and policy.

This document defines the split between validation and authorization:

- Validation determines whether a proposed action is structurally and semantically usable.
- Authorization determines whether that valid action may execute automatically without another chat confirmation.

The automation settings belong in the control plane because the decision depends on runtime state: user settings, workspace policy, target sessions, validation status, private-session visibility, and external side effects.

## Current scaffold

Implemented files:

- `control-plane/api/services/platform_settings.py`
  - Adds `AutomationSettings` under persisted `PlatformSettings`.
- `control-plane/api/services/action_authorization.py`
  - Adds `authorize_action()` and models for authorization preview.
- `control-plane/api/routes/session_graph/settings.py`
  - Exposes automation settings and `/api/session-graph/authorization/preview`.
- `control-plane/tests/test_action_authorization.py`
  - Covers auto-push confirmation, validation gating, auto-commit authorization, and settings roundtrip.

## Automation settings

```json
{
  "auto_apply_patch": false,
  "auto_run_tests": true,
  "auto_run_lint": true,
  "auto_run_typecheck": true,
  "auto_commit": false,
  "auto_push": false,
  "auto_create_pr": false,
  "auto_merge_pr": false,
  "auto_deploy": false,
  "auto_use_secret": false,
  "require_validation_before_external_side_effect": true,
  "require_private_session_confirmation": true,
  "certainty_thresholds": {}
}
```

Defaults are conservative. Read-only and local validation actions can be automated sooner. External side effects remain disabled until the user explicitly enables them.

## Authorization states

The service returns three practical states:

1. `authorized=true`
   - The action can execute without another chat confirmation.
2. `requires_user_confirmation=true`
   - The action is otherwise allowed, but the matching automation toggle is disabled or the session requires explicit confirmation.
3. `blocked=true`
   - The action must not execute, even if the UI would normally skip confirmation.

Examples:

- `push` with `auto_push=false` returns `requires_user_confirmation=true`.
- `push` with `auto_push=true` but no validation returns `blocked=true`.
- `commit` with `auto_commit=true` and validation passed returns `authorized=true`.

## Execution-loop placement

The intended pipeline is:

```text
LLM proposes next action
  -> agent-core/schema validator checks shape, params, stakes, and target sessions
  -> ai-agent-workstation authorization checks automation settings and runtime policy
  -> executor runs the action only if authorized or explicitly confirmed
```

The LLM must never be treated as the source of authorization. It can propose actions. The control plane authorizes or blocks them.

## UI intent

The session settings UI should expose toggles such as:

- Auto apply patch
- Auto run tests
- Auto run lint
- Auto run typecheck
- Auto commit
- Auto push
- Auto create PR
- Auto deploy

The UI should also show why an action is blocked or confirmation-required. Use `/api/session-graph/authorization/preview` before executing a proposed action when the user needs an explanation.

## Non-goals

This scaffold does not yet execute actions. It does not replace validation. It does not bypass branch protection, repository permissions, or future workspace authorization. It only creates the control-plane authorization layer that the execution loop and UI can wire into.

## Future work

- Add per-session overrides instead of only platform-level defaults.
- Add workspace/user ownership to automation settings.
- Integrate authorization into the actual executor loop.
- Add UI controls to session settings panels.
- Add audit events when an action is automatically authorized, confirmation-required, or blocked.
