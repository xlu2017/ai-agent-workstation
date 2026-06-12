# Session Automation UI

## Intent

The session chat should not force a user to confirm every action once the user has intentionally enabled automation. This UI scaffold exposes the control-plane automation settings and previews whether a proposed action would run automatically, require confirmation, or be blocked.

This complements the backend authorization scaffold:

- `GET /api/session-graph/settings/automation`
- `PUT /api/session-graph/settings/automation`
- `POST /api/session-graph/authorization/preview`

## Implemented UI files

- `control-plane/web/src/components/session-graph/AutomationSettingsPanel.tsx`
  - Fetches and saves automation settings.
  - Shows toggles for auto patch/test/lint/typecheck/commit/push/PR/deploy/secret usage.
  - Provides an authorization preview surface for representative actions.
  - Distinguishes authorized, confirmation-required, and blocked outcomes.

- `control-plane/web/src/components/session-graph/SessionGraphExplorer.tsx`
  - Wires `AutomationSettingsPanel` into the right-side graph context panel.
  - Uses the selected session as the preview target when available.

- `control-plane/web/src/components/session-graph/session-graph-ux.css`
  - Adds visual treatment for automation settings, risk badges, and authorization preview states.

## Product behavior

The UI is intentionally scoped to the session graph explorer first because authorization depends on target session identity and graph context.

The user can:

1. Enable or disable automation gates.
2. Save automation settings to the control plane.
3. Select a representative action such as run tests, apply patch, commit, or push.
4. Preview whether that action would execute automatically for the selected session.
5. See whether the outcome is authorized, requires confirmation, or blocked.

## Design rule

The UI does not authorize actions by itself. It only changes persisted settings and asks the control plane for an authorization decision.

Pipeline:

```text
LLM proposes action
  -> validation checks schema and semantics
  -> authorization checks automation settings and session policy
  -> executor runs only when authorized or explicitly confirmed
```

## Current limitations

- The UI uses platform-level automation settings, not per-session overrides.
- The preview uses representative action presets rather than live pending actions from the executor loop.
- The actual execution loop is not yet wired to call authorization before every action.
- The settings surface is located in the session graph explorer, not the main workspace settings page.

## Next integration steps

1. Add per-session automation overrides to the session graph model.
2. Surface the same panel in the main settings page once the settings page is decomposed enough to avoid whole-file edits.
3. Wire the executor loop to call `/api/session-graph/authorization/preview` or its internal service equivalent before executing actions.
4. Emit audit events when authorization allows, blocks, or asks for confirmation.
5. Replace representative presets with the current pending next action when the next-action controller is connected.
