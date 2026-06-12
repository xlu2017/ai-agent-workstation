"""UI capability contract.

This route is the backend source of truth for whether a visible UI affordance
should be rendered, disabled, or omitted.  CSS must not be used as the durable
feature-control layer for this platform because route availability, mutation
support, authorization, and workflow state are product semantics, not styling.

The initial registry is intentionally static.  Future work can compute these
flags from service health, organization policy, user permissions, workspace
configuration, and installed integrations without changing frontend rendering
contracts.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ui-capabilities"])

Capability = dict[str, object]


def _capability(
    *,
    key: str,
    label: str,
    area: str,
    enabled: bool,
    visibility: str,
    reason: str,
    endpoints: list[str] | None = None,
    routes: list[str] | None = None,
    local_actions: list[str] | None = None,
    external_targets: list[str] | None = None,
    intent: str,
) -> Capability:
    """Build a serializable capability record with a consistent shape."""
    return {
        "key": key,
        "label": label,
        "area": area,
        "enabled": enabled,
        "visibility": visibility,
        "reason": reason,
        "endpoints": endpoints or [],
        "routes": routes or [],
        "local_actions": local_actions or [],
        "external_targets": external_targets or [],
        "intent": intent,
    }


CAPABILITIES: list[Capability] = [
    _capability(
        key="settings.open",
        label="Open settings",
        area="workspace",
        enabled=True,
        visibility="render",
        reason="Settings is backed by concrete settings panels and existing inspection endpoints.",
        routes=["/settings"],
        endpoints=["/api/health", "/api/services", "/api/session-graph/settings/observability"],
        intent="Workspace settings must stay visible because it routes to implemented backend-backed panels.",
    ),
    _capability(
        key="workspace.invite_members",
        label="Invite members",
        area="workspace",
        enabled=False,
        visibility="omit",
        reason="No invite-members endpoint, membership model, or organization role model exists yet.",
        intent="Do not render invites until users, roles, and membership mutations are implemented.",
    ),
    _capability(
        key="workspace.create",
        label="Create workspace",
        area="workspace",
        enabled=False,
        visibility="omit",
        reason="No workspace creation endpoint, workspace model, or auth boundary exists yet.",
        intent="Do not render workspace creation until the platform can persist and authorize workspaces.",
    ),
    _capability(
        key="auth.logout",
        label="Log out",
        area="workspace",
        enabled=False,
        visibility="omit",
        reason="No authenticated session or logout endpoint exists yet.",
        intent="Do not render logout as a dead control; add it only with real auth/session semantics.",
    ),
    _capability(
        key="sidebar.ask",
        label="Ask",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="The destination is not wired to a distinct backend-backed ask surface.",
        intent="Ask should be restored as a real route or panel, not hidden through CSS selectors.",
    ),
    _capability(
        key="sidebar.knowledge",
        label="Knowledge",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="Knowledge exists inside settings, but the sidebar item currently routes too broadly.",
        endpoints=["/api/knowledge", "/api/knowledge/proposed"],
        intent="Restore this when the sidebar target opens a specific knowledge surface.",
    ),
    _capability(
        key="sidebar.review",
        label="Review",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="No review dashboard route or review-action mutation endpoint exists yet.",
        intent="Review should be visible only after review data and review mutations are implemented.",
    ),
    _capability(
        key="sidebar.automations",
        label="Automations",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="No automation route or scheduling endpoint exists in this control plane yet.",
        intent="Automations require a scheduler contract before the nav item is meaningful.",
    ),
    _capability(
        key="recent.placeholder_actions",
        label="Recent menu placeholder actions",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="The recent menu action row is informational and does not trigger a meaningful operation.",
        intent="Remove placeholder recent-menu actions until each action has a real route or mutation.",
    ),
    _capability(
        key="help.open",
        label="Open help",
        area="sidebar",
        enabled=False,
        visibility="omit",
        reason="No help route, docs panel, or external help target is wired yet.",
        intent="Render help only when it opens a concrete local docs surface or external documentation target.",
    ),
    _capability(
        key="session.decision.submit",
        label="Submit decision answer",
        area="session",
        enabled=False,
        visibility="omit",
        reason="Historical decision options are display-only; there is no answer-submission endpoint.",
        intent="Decision controls must be rendered by capability, then wired to a mutation endpoint.",
    ),
    _capability(
        key="session.artifact_tab.create",
        label="Create artifact tab",
        area="session",
        enabled=False,
        visibility="omit",
        reason="The plus control has no tab creation handler or persistence endpoint.",
        intent="Do not expose tab creation until tabs have a backing model and creation mutation.",
    ),
    _capability(
        key="session.review_actions",
        label="Review action buttons",
        area="session",
        enabled=False,
        visibility="omit",
        reason="Review buttons are not backed by routed links or API-backed handlers.",
        intent="Review actions should be restored with route or mutation semantics, not CSS display rules.",
    ),
    _capability(
        key="session_graph.crud",
        label="Session graph CRUD",
        area="session_graph",
        enabled=True,
        visibility="render",
        reason="Graph CRUD calls concrete session-graph endpoints for sessions and edges.",
        endpoints=["/api/session-graph/sessions", "/api/session-graph/edges"],
        intent="Graph mutation controls are valid because they use backend session-graph mutations.",
    ),
    _capability(
        key="services.update_latest",
        label="Update latest for repo-backed services",
        area="services",
        enabled=True,
        visibility="render",
        reason="Repo-backed service rows call the update-latest service endpoint.",
        endpoints=["/api/v2/services/{name}/update-latest"],
        intent="Service update buttons may render when service rows report repo_backed and update_supported.",
    ),
]


@router.get("/api/ui/capabilities")
def get_ui_capabilities() -> dict[str, object]:
    """Return feature gates used by the frontend before rendering controls."""
    return {
        "version": 1,
        "intent": (
            "Use backend capabilities and typed React gates for product behavior. "
            "Use CSS only for visual presentation and transitional quarantine styles."
        ),
        "capabilities": CAPABILITIES,
    }
