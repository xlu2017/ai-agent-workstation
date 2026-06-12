"""Common graph workflow route."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/workflow/dev")
def dev_workflow() -> dict[str, object]:
    return {
        "workflow": {
            "stages": ["repo", "goal", "adapter", "work", "runtime", "validation", "pull_request"],
            "edges": ["mounted_under", "implements", "component_of", "validates", "produces"],
            "canonical_model": "/api/session-graph",
            "legacy_runtime_sessions": "deprecated_without_migration",
            "non_session_rule": "Attach transient details to durable graph sessions as events, facets, projections, or artifacts.",
        }
    }
