"""Common graph workflow route."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/workflow/dev")
def dev_workflow() -> dict[str, object]:
    return {
        "stages": ["repo", "goal", "adapter", "work", "runtime", "validation", "pull_request"],
        "edges": ["mounted_under", "implements", "component_of", "validates", "produces"],
        "canonical_model": "/api/session-graph",
    }
