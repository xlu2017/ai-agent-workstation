import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))


def test_auto_push_disabled_requires_confirmation():
    from api.models.session_graph import ActionStakes, SessionGraphSnapshot, SessionKind, SessionRecord
    from api.services.action_authorization import ActionAuthorizationContext, ProposedAction, authorize_action
    from api.services.platform_settings import AutomationSettings

    repo = SessionRecord(id="repo-1", kind=SessionKind.REPO, title="Repo")
    action = ProposedAction(
        decision="execute",
        task_name="push",
        target_session_ids=["repo-1"],
        certainty=0.99,
        stakes=ActionStakes.EXTERNAL_SIDE_EFFECT,
    )

    result = authorize_action(
        action,
        SessionGraphSnapshot(sessions=[repo]),
        ActionAuthorizationContext(
            validation_passed=True,
            automation_settings=AutomationSettings(auto_push=False),
        ),
    )

    assert not result.authorized
    assert result.requires_user_confirmation
    assert result.required_setting == "auto_push"


def test_auto_push_enabled_requires_validation():
    from api.models.session_graph import ActionStakes, SessionGraphSnapshot, SessionKind, SessionRecord
    from api.services.action_authorization import ActionAuthorizationContext, ProposedAction, authorize_action
    from api.services.platform_settings import AutomationSettings

    repo = SessionRecord(id="repo-1", kind=SessionKind.REPO, title="Repo")
    action = ProposedAction(
        decision="execute",
        task_name="push",
        target_session_ids=["repo-1"],
        certainty=0.99,
        stakes=ActionStakes.EXTERNAL_SIDE_EFFECT,
    )

    result = authorize_action(
        action,
        SessionGraphSnapshot(sessions=[repo]),
        ActionAuthorizationContext(
            validation_passed=False,
            automation_settings=AutomationSettings(auto_push=True),
        ),
    )

    assert not result.authorized
    assert result.blocked
    assert "validation" in result.reason.lower()


def test_auto_commit_enabled_authorizes_after_validation():
    from api.models.session_graph import ActionStakes, SessionGraphSnapshot, SessionKind, SessionRecord
    from api.services.action_authorization import ActionAuthorizationContext, ProposedAction, authorize_action
    from api.services.platform_settings import AutomationSettings

    repo = SessionRecord(id="repo-1", kind=SessionKind.REPO, title="Repo")
    action = ProposedAction(
        decision="execute",
        task_name="commit",
        target_session_ids=["repo-1"],
        certainty=0.99,
        stakes=ActionStakes.EXTERNAL_SIDE_EFFECT,
    )

    result = authorize_action(
        action,
        SessionGraphSnapshot(sessions=[repo]),
        ActionAuthorizationContext(
            validation_passed=True,
            automation_settings=AutomationSettings(auto_commit=True),
        ),
    )

    assert result.authorized
    assert not result.requires_user_confirmation
    assert not result.blocked


def test_platform_settings_roundtrip_includes_automation(tmp_path):
    from api.services.platform_settings import AutomationSettings, PlatformSettings, load_platform_settings, save_platform_settings

    path = tmp_path / "settings.json"
    save_platform_settings(
        PlatformSettings(automation=AutomationSettings(auto_commit=True, auto_push=True)),
        path=path,
    )

    loaded = load_platform_settings(path=path)
    assert loaded.automation.auto_commit is True
    assert loaded.automation.auto_push is True
