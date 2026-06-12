# Mandatory agent-core next-action calls

## Correction

The mandatory decision layer is not an Agent-Dash-specific component. The source of next-action intelligence is `agent-core`.

`jubilant-goggles` owns execution, runtime validation, authorization, worktrees, UI, and events. `agent-core` owns advisory next-action recommendation and action contract intelligence.

## Invariant

Every platform action decision must call the agent-core next-action system before execution.

Executors must not choose the next action. Deterministic execution may still be used, but only after agent-core has been consulted for the action decision.

## Current scaffold

Implemented scaffold file:

- `control-plane/execution/next_action_orchestrator.py`

It wraps `AgentCoreClient.recommend_next()` and returns a normalized decision object that current workflow code can use before runtime validation and execution.

## Intended pipeline

```text
observe current session state
  -> build next-action request
  -> call agent-core /actions/recommend-next
  -> normalize recommended action
  -> validate action contract and runtime policy
  -> authorize automation settings
  -> execute through the selected execution adapter
  -> record outcome back to agent-core
  -> repeat
```

## Why mandatory

The platform is optimized for long-horizon autonomous work. It is acceptable for each action to take longer if the system can keep choosing the next useful step for hours without stopping unnecessarily.

The desired behavior is not a static plan executing blindly. It is a rolling loop:

```text
observe -> recommend next -> validate -> authorize -> execute -> record outcome -> observe again
```

## Configuration

```text
AGENT_CORE_NEXT_ACTION_REQUIRED=true
AGENT_CORE_NEXT_ACTION_STRICT=false
```

`AGENT_CORE_NEXT_ACTION_REQUIRED` should default to true.

`AGENT_CORE_NEXT_ACTION_STRICT` controls compatibility mode. When false, existing flows can continue if agent-core is temporarily unavailable, but the result is marked as compatibility mode. When true, execution is blocked if the agent-core next-action call cannot be completed.

## Integration TODOs

1. Wire `MandatoryNextActionOrchestrator` into `PlanExecutor` before runtime validation.
2. Add live event metadata showing the agent-core recommendation for each action.
3. Add tests proving that every plan step consults the orchestrator.
4. Replace static plan iteration for open-ended sessions with rolling next-action cycles.
5. Route authorization through `action_authorization.py` after the next-action decision and before execution.
6. Add UI indicators for compatibility mode versus strict agent-core-gated execution.

## Non-goals

This scaffold does not make agent-core execute actions. It does not make agent-core authorize side effects. It does not bypass runtime validation. It only makes next-action recommendation mandatory in the decision path.
