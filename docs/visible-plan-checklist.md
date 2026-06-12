# Visible plan checklist

## Intent

The plan is a real action because it creates user-visible UI state. It should appear as a checklist component in the frontend. Completed planned steps are checked after action outcomes are recorded.

## Execution rule

The executor must not follow the plan directly. The only source of executable next actions is agent-core recommend-next.

```text
visible plan -> informs recommend-next
recommend-next -> selects one executable action
outcome -> checks matching plan steps
recommend-next deviation -> revises visible plan
```

## Scaffolded UI

- `control-plane/web/src/components/plan/VisiblePlanChecklist.tsx`
- `control-plane/web/src/components/plan/visible-plan-checklist.css`

The component accepts a `VisiblePlanArtifact` and renders:

- plan goal
- active/completed/stale status
- progress bar
- planned steps
- completed checkmarks
- blocked/active/skipped states
- completion evidence

## TODO

1. Add a backend endpoint that proxies agent-core visible plan state.
2. Mount the component in the session chat sidebar or worklog panel.
3. Subscribe to action outcome events and refresh plan state after each outcome.
4. Display plan revision events when recommend-next deviates.
5. Ensure the execution loop calls only recommend-next for executable actions.
