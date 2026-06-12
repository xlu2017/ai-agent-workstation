# Dynamic context projection budgets

Session composition is intentionally more flexible than strict hierarchy. A repo session, app session, vendor session, runtime session, work session, and goal session can be mounted or adapted under one another without rewriting the source session identity. The safety mechanism is the context projection budget.

A projection budget is not a measure of the source session size. It is a task-scoped envelope for how much source context may enter the active target. The active goal must remain dominant.

## Core invariant

```text
Do not let the mounted session dominate the active goal.
Only project enough context to solve the current target.
```

This prevents context pollution while still allowing radical session composition. A whole external repository can be mounted under a tiny goal, but the projection should expose selected capabilities, interfaces, mappings, or recent failures rather than importing the whole repository history into the active task.

## Initial scaffolded profiles

| Profile | Intended use | Budget |
| --- | --- | --- |
| `direct_ui_action` | Browser, desktop, and immediate UI operations | 1000 tokens, 0 files, 5 events |
| `known_repo_bug_fix` | Bug fix in a known repo area | 6000 tokens, 12 files, 50 events |
| `architecture_planning` | Design, planning, refactor, and scaffold tasks | 20000 tokens, 60 files, 200 events |
| `cross_repo_integration` | Integrating one repo/session into another | 22000 tokens, selected interface files, adapter mappings, recent failures |
| `focused_mount_projection` | Broad source mounted under focused goal/work/question | 4000 tokens, 12 files, 50 events |
| `general_session_context` | Same-scale session graph references when no narrower task profile matches | 12000 tokens, 40 files, 200 events |

The numeric values are scaffold defaults. They are encoded as profiles so they can later become dynamic per model, executor, repo size, failure history, user preference, task risk, and measured retrieval precision.

## Selection behavior

The control plane selects a profile from the mount/adapt request:

```text
direct UI terms or runtime target
  -> direct_ui_action

cross-repo, adapter, API, interface, port, wrap, vendor, or component mount
  -> cross_repo_integration

architecture, design, scaffold, planning, workflow, system, or refactor intent
  -> architecture_planning

bug, fix, failing, failure, error, test, or regression intent
  -> known_repo_bug_fix

broad source under focused target
  -> focused_mount_projection

otherwise
  -> general_session_context
```

The broad-source/focused-target guard applies when a `repo`, `app`, or `container` session is mounted under a `goal`, `work`, or `question` session. That guard adds explicit evidence and excludes unrelated UI, deployment, plugin, historical-noise, and unrelated-capability context.

## Projection evidence

The current API model has a numeric `ContextProjectionBudget`, so named profiles are exposed through projection evidence and rationale for now:

```json
{
  "budget": {
    "max_tokens": 4000,
    "max_files": 12,
    "max_events": 50,
    "recency_days": 30
  },
  "evidence": [
    "budget_profile:focused_mount_projection",
    "dominance_guard:broad_source_under_focused_target"
  ]
}
```

A later API schema can promote `budget_profile` into a typed budget field without changing the selection rules.

## Future dynamic inputs

The next version should compute the budget from measured conditions instead of static profile defaults:

```text
task classifier output
source and target session kinds
source graph size
active target scope
retrieval confidence
known relevant files
adapter mapping confidence
recent failure density
validation risk
model context window
executor cost policy
user/project budget policy
```

The static profiles are therefore not the final budgeting system. They are a schema-stable scaffold that makes projection decisions visible, testable, and replaceable.
