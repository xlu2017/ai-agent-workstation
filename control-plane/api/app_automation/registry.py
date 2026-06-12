"""Registry for vendored app automation tools and seed app actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.app_automation.models import AppAction, VendorTool

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = CONTROL_PLANE_ROOT / "vendor" / "app-automation" / "manifest.json"


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open() as f:
        return json.load(f)


def list_vendor_tools() -> list[VendorTool]:
    manifest = load_manifest()
    return [VendorTool(**tool) for tool in manifest.get("selected_tools", [])]


def vendor_installed(tool: VendorTool) -> bool:
    target = CONTROL_PLANE_ROOT.parent / tool.target_dir
    return (target / ".git").exists() or (target / "package.json").exists() or (target / "pyproject.toml").exists()


def vendor_status() -> list[dict[str, Any]]:
    result = []
    for tool in list_vendor_tools():
        target = CONTROL_PLANE_ROOT.parent / tool.target_dir
        result.append({
            **tool.model_dump(),
            "installed": vendor_installed(tool),
            "target_exists": target.exists(),
        })
    return result


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": True}


SEED_ACTIONS: list[AppAction] = [
    AppAction(
        id="github.create_issue",
        app_id="github",
        label="Create GitHub issue",
        description="Create an issue in a GitHub repository.",
        execution_kind="mcp",
        preferred_vendor="mcp_servers",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, ["repo", "title"]),
    ),
    AppAction(
        id="github.search_repo",
        app_id="github",
        label="Search GitHub repository",
        description="Search code, issues, or pull requests in GitHub.",
        execution_kind="mcp",
        preferred_vendor="mcp_servers",
        risk="read_only",
        approval="none",
        input_schema=_schema({"repo": {"type": "string"}, "query": {"type": "string"}, "kind": {"type": "string"}}, ["repo", "query"]),
    ),
    AppAction(
        id="slack.send_message",
        app_id="slack",
        label="Send Slack message",
        description="Send a Slack channel or DM message.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"channel": {"type": "string"}, "text": {"type": "string"}}, ["channel", "text"]),
    ),
    AppAction(
        id="gmail.search_email",
        app_id="gmail",
        label="Search Gmail",
        description="Search Gmail messages with a query.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="read_only",
        approval="none",
        input_schema=_schema({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    ),
    AppAction(
        id="google_calendar.create_event",
        app_id="google_calendar",
        label="Create calendar event",
        description="Create a Google Calendar event.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "attendees": {"type": "array"}}, ["title", "start", "end"]),
    ),
    AppAction(
        id="google_sheets.append_row",
        app_id="google_sheets",
        label="Append row to Google Sheet",
        description="Append a row to a Google Sheet.",
        execution_kind="workflow",
        preferred_vendor="activepieces",
        risk="modification",
        approval="preview",
        input_schema=_schema({"spreadsheet_id": {"type": "string"}, "sheet": {"type": "string"}, "row": {"type": "array"}}, ["spreadsheet_id", "row"]),
    ),
    AppAction(
        id="notion.create_page",
        app_id="notion",
        label="Create Notion page",
        description="Create a page in a Notion database or workspace.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="modification",
        approval="preview",
        input_schema=_schema({"parent": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}}, ["title"]),
    ),
    AppAction(
        id="linear.create_issue",
        app_id="linear",
        label="Create Linear issue",
        description="Create a Linear issue.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"team": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}, ["team", "title"]),
    ),
    AppAction(
        id="jira.create_issue",
        app_id="jira",
        label="Create Jira issue",
        description="Create a Jira issue.",
        execution_kind="workflow",
        preferred_vendor="activepieces",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"project": {"type": "string"}, "summary": {"type": "string"}, "description": {"type": "string"}}, ["project", "summary"]),
    ),
    AppAction(
        id="discord.send_message",
        app_id="discord",
        label="Send Discord message",
        description="Send a Discord message.",
        execution_kind="workflow",
        preferred_vendor="activepieces",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"channel": {"type": "string"}, "text": {"type": "string"}}, ["channel", "text"]),
    ),
    AppAction(
        id="hubspot.create_contact",
        app_id="hubspot",
        label="Create HubSpot contact",
        description="Create a HubSpot contact.",
        execution_kind="api",
        preferred_vendor="composio",
        risk="external_side_effect",
        approval="required",
        input_schema=_schema({"email": {"type": "string"}, "firstname": {"type": "string"}, "lastname": {"type": "string"}}, ["email"]),
    ),
    AppAction(
        id="web.perform_task",
        app_id="web",
        label="Perform browser task",
        description="Use browser automation for an arbitrary web-app task.",
        execution_kind="browser",
        preferred_vendor="stagehand",
        risk="modification",
        approval="preview",
        input_schema=_schema({"url": {"type": "string"}, "instruction": {"type": "string"}}, ["instruction"]),
    ),
    AppAction(
        id="web.visual_task",
        app_id="web",
        label="Perform visual browser task",
        description="Use visual browser automation when DOM automation is brittle.",
        execution_kind="visual_browser",
        preferred_vendor="skyvern",
        risk="modification",
        approval="preview",
        input_schema=_schema({"url": {"type": "string"}, "instruction": {"type": "string"}}, ["instruction"]),
    ),
]


def list_actions() -> list[AppAction]:
    vendor_by_id = {tool.id: tool for tool in list_vendor_tools()}
    actions = []
    for action in SEED_ACTIONS:
        vendor = vendor_by_id.get(action.preferred_vendor)
        action_copy = action.model_copy(deep=True)
        if vendor and vendor_installed(vendor):
            action_copy.available = True
            action_copy.unavailable_reason = ""
        elif vendor:
            action_copy.available = False
            action_copy.unavailable_reason = f"Vendor runtime '{vendor.id}' has not been vendored into {vendor.target_dir}."
        actions.append(action_copy)
    return actions


def get_action(action_id: str) -> AppAction | None:
    for action in list_actions():
        if action.id == action_id:
            return action
    return None
