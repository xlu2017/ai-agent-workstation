from __future__ import annotations

from typing import Any

from api.app_automation.models import AppAction
from api.app_automation.registry import list_vendor_tools, vendor_installed


VENDOR_PROFILES: dict[str, dict[str, Any]] = {
    "composio": {
        "layer": "api",
        "position": 10,
        "best_for": ["stable SaaS APIs", "read only API calls", "account scoped app actions"],
        "not_best_for": ["multi step workflows", "unstructured browser pages"],
        "handoff_to": ["mcp_servers", "activepieces", "stagehand"],
    },
    "mcp_servers": {
        "layer": "mcp",
        "position": 20,
        "best_for": ["tool protocol references", "git and filesystem examples", "local service tools"],
        "not_best_for": ["unreviewed production side effects"],
        "handoff_to": ["composio", "activepieces"],
    },
    "activepieces": {
        "layer": "workflow",
        "position": 30,
        "best_for": ["connector workflows", "approval flows", "app to app automation"],
        "not_best_for": ["single low latency API reads", "visual browser repair"],
        "handoff_to": ["n8n", "composio", "mcp_servers"],
    },
    "n8n": {
        "layer": "workflow",
        "position": 40,
        "best_for": ["deterministic long workflows", "webhooks", "self hosted integrations"],
        "not_best_for": ["small inline actions", "license sensitive redistribution without review"],
        "handoff_to": ["activepieces", "composio"],
    },
    "stagehand": {
        "layer": "browser",
        "position": 50,
        "best_for": ["browser tasks with DOM access", "form fill", "web app workflows"],
        "not_best_for": ["API covered apps", "brittle visual only pages"],
        "handoff_to": ["browser_use", "skyvern"],
    },
    "browser_use": {
        "layer": "browser",
        "position": 60,
        "best_for": ["Python browser automation", "natural language web navigation"],
        "not_best_for": ["stable SaaS API calls"],
        "handoff_to": ["stagehand", "skyvern"],
    },
    "skyvern": {
        "layer": "visual_browser",
        "position": 70,
        "best_for": ["visual browser fallback", "unstable DOMs", "screenshots plus browser tasks"],
        "not_best_for": ["API covered apps", "low risk read only calls"],
        "handoff_to": ["stagehand", "browser_use"],
    },
}


ACTION_VENDOR_PREFERENCES: dict[str, list[str]] = {
    "github.create_issue": ["mcp_servers", "composio", "activepieces"],
    "github.search_repo": ["mcp_servers", "composio"],
    "slack.send_message": ["composio", "activepieces", "n8n"],
    "gmail.search_email": ["composio", "mcp_servers", "activepieces"],
    "google_calendar.create_event": ["composio", "activepieces", "n8n"],
    "google_sheets.append_row": ["activepieces", "composio", "n8n"],
    "notion.create_page": ["composio", "activepieces", "n8n"],
    "linear.create_issue": ["composio", "activepieces"],
    "jira.create_issue": ["activepieces", "composio", "n8n"],
    "discord.send_message": ["activepieces", "composio", "n8n"],
    "hubspot.create_contact": ["composio", "activepieces", "n8n"],
    "web.perform_task": ["stagehand", "browser_use", "skyvern"],
    "web.visual_task": ["skyvern", "stagehand", "browser_use"],
}


def vendor_profile_matrix() -> list[dict[str, Any]]:
    tools = {tool.id: tool for tool in list_vendor_tools()}
    rows: list[dict[str, Any]] = []
    for vendor_id, profile in sorted(VENDOR_PROFILES.items(), key=lambda item: item[1]["position"]):
        tool = tools.get(vendor_id)
        rows.append({
            "vendor": vendor_id,
            "layer": profile["layer"],
            "position": profile["position"],
            "best_for": profile["best_for"],
            "not_best_for": profile["not_best_for"],
            "handoff_to": profile["handoff_to"],
            "installed": vendor_installed(tool) if tool else False,
            "target_dir": tool.target_dir if tool else None,
            "license": tool.license if tool else None,
        })
    return rows


def route_candidates_for_action(action: AppAction) -> list[dict[str, Any]]:
    tools = {tool.id: tool for tool in list_vendor_tools()}
    candidate_ids = ACTION_VENDOR_PREFERENCES.get(action.id, [action.preferred_vendor])
    if action.preferred_vendor not in candidate_ids:
        candidate_ids = [action.preferred_vendor, *candidate_ids]
    candidates: list[dict[str, Any]] = []
    for index, vendor_id in enumerate(candidate_ids, start=1):
        tool = tools.get(vendor_id)
        profile = VENDOR_PROFILES.get(vendor_id, {})
        candidates.append({
            "rank": index,
            "vendor": vendor_id,
            "layer": profile.get("layer", action.execution_kind),
            "installed": vendor_installed(tool) if tool else False,
            "target_dir": tool.target_dir if tool else None,
            "reason": _candidate_reason(action, vendor_id, profile),
            "status": "ready_for_adapter" if tool and vendor_installed(tool) else "source_missing",
        })
    return candidates


def build_action_plan(action: AppAction) -> dict[str, Any]:
    candidates = route_candidates_for_action(action)
    selected = next((candidate for candidate in candidates if candidate["installed"]), candidates[0] if candidates else None)
    return {
        "action_id": action.id,
        "app_id": action.app_id,
        "risk": action.risk,
        "approval": action.approval,
        "preferred_vendor": action.preferred_vendor,
        "selected_vendor": selected["vendor"] if selected else None,
        "selected_layer": selected["layer"] if selected else None,
        "candidates": candidates,
        "execution_ladder": ["api", "mcp", "workflow", "browser", "visual_browser", "desktop"],
        "coordination_notes": _coordination_notes(action),
    }


def _candidate_reason(action: AppAction, vendor_id: str, profile: dict[str, Any]) -> str:
    layer = profile.get("layer", action.execution_kind)
    if vendor_id == action.preferred_vendor:
        return f"Preferred vendor for {action.id}; {layer} layer matches initial catalog selection."
    return f"Fallback for {action.id}; use when preferred vendor is unavailable or weaker for this app surface."


def _coordination_notes(action: AppAction) -> list[str]:
    notes = [
        "Try native API or MCP before workflow/browser automation when available.",
        "Use workflow vendors for multi step repeatable automations.",
        "Use browser vendors when no reliable API or MCP surface exists.",
        "Use visual browser only after DOM/browser automation is insufficient.",
    ]
    if action.risk == "external_side_effect":
        notes.append("External side effects require approval before live execution.")
    elif action.approval == "preview":
        notes.append("Preview before live execution unless the session policy explicitly permits it.")
    return notes
