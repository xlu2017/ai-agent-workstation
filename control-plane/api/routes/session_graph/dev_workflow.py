"""Common graph workflow route."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/workflow/dev")
def dev_workflow() -> dict[str, object]:
    return {
        "workflow": {
            "stages": ["goal_or_question", "repo_optional", "adapter", "work", "runtime", "validation", "pull_request"],
            "edges": ["mounted_under", "implements", "component_of", "validates", "produces"],
            "canonical_model": "/api/session-graph",
            "legacy_runtime_sessions": "deprecated_without_migration",
            "repo_required_at_start": False,
            "repo_required_before_execution": True,
            "repo_requirement_note": "Users may start unscoped sessions. Repo scope is required only before repo-dependent execution such as file edits, tests, runtime worktrees, or PR output.",
            "non_session_rule": "Attach transient details to durable graph sessions as events, facets, projections, or artifacts.",
        }
    }
