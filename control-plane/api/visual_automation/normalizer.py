"""Normalize provider-specific computer-use outputs into platform actions."""

from __future__ import annotations

from typing import Any

from api.visual_automation.models import VisualAction, VisualProviderId


def _anthropic_actions(raw: dict[str, Any]) -> list[VisualAction]:
    actions: list[VisualAction] = []
    for block in raw.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "computer":
            continue
        payload = block.get("input", {}) or {}
        action = payload.get("action")
        coordinate = payload.get("coordinate") or []
        if action == "screenshot":
            actions.append(VisualAction(kind="screenshot"))
        elif action in {"left_click", "right_click", "middle_click"}:
            button = action.replace("_click", "")
            actions.append(VisualAction(kind="click", button=button, x=coordinate[0] if len(coordinate) > 0 else None, y=coordinate[1] if len(coordinate) > 1 else None))
        elif action == "double_click":
            actions.append(VisualAction(kind="double_click", x=coordinate[0] if len(coordinate) > 0 else None, y=coordinate[1] if len(coordinate) > 1 else None))
        elif action == "type":
            actions.append(VisualAction(kind="type", text=payload.get("text", "")))
        elif action == "key":
            actions.append(VisualAction(kind="key", text=payload.get("text", "")))
        elif action == "scroll":
            actions.append(VisualAction(kind="scroll", x=coordinate[0] if len(coordinate) > 0 else None, y=coordinate[1] if len(coordinate) > 1 else None, direction=payload.get("scroll_direction"), amount=payload.get("scroll_amount")))
        elif action == "left_click_drag":
            start = payload.get("start_coordinate") or []
            actions.append(VisualAction(kind="drag", from_xy=(start[0], start[1]) if len(start) >= 2 else None, to_xy=(coordinate[0], coordinate[1]) if len(coordinate) >= 2 else None))
        elif action == "wait":
            actions.append(VisualAction(kind="wait", duration_seconds=payload.get("duration")))
        elif action == "zoom":
            region = payload.get("region")
            actions.append(VisualAction(kind="zoom", region=tuple(region) if isinstance(region, list) and len(region) == 4 else None))
    return actions


def _gemini_actions(raw: dict[str, Any]) -> list[VisualAction]:
    actions: list[VisualAction] = []
    candidates = raw.get("candidates", []) if isinstance(raw.get("candidates"), list) else []
    for candidate in candidates:
        parts = (((candidate or {}).get("content") or {}).get("parts") or [])
        for part in parts:
            function_call = part.get("functionCall") or part.get("function_call") if isinstance(part, dict) else None
            if not function_call:
                continue
            name = function_call.get("name", "")
            args = function_call.get("args", {}) or {}
            x = args.get("x")
            y = args.get("y")
            if name in {"click_at", "left_click_at"}:
                actions.append(VisualAction(kind="click", button="left", x=x, y=y))
            elif name == "type_text_at":
                actions.append(VisualAction(kind="click", button="left", x=x, y=y))
                actions.append(VisualAction(kind="type", text=args.get("text", "")))
            elif name == "key_combination":
                actions.append(VisualAction(kind="key", text=args.get("keys", "")))
            elif name == "scroll_at":
                actions.append(VisualAction(kind="scroll", x=x, y=y, direction=args.get("direction"), amount=args.get("amount")))
            elif name == "wait":
                actions.append(VisualAction(kind="wait", duration_seconds=args.get("duration")))
    return actions


def _openai_actions(raw: dict[str, Any]) -> list[VisualAction]:
    actions: list[VisualAction] = []
    output = raw.get("output", []) if isinstance(raw.get("output"), list) else []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"computer_call", "tool_call"}:
            continue
        action = item.get("action") or {}
        action_type = action.get("type") or item.get("name")
        if action_type in {"click", "left_click"}:
            actions.append(VisualAction(kind="click", button=action.get("button", "left"), x=action.get("x"), y=action.get("y")))
        elif action_type == "double_click":
            actions.append(VisualAction(kind="double_click", x=action.get("x"), y=action.get("y")))
        elif action_type == "type":
            actions.append(VisualAction(kind="type", text=action.get("text", "")))
        elif action_type == "keypress":
            actions.append(VisualAction(kind="key", text="+".join(action.get("keys", []))))
        elif action_type == "scroll":
            actions.append(VisualAction(kind="scroll", x=action.get("x"), y=action.get("y"), direction=action.get("direction"), amount=action.get("amount")))
        elif action_type == "wait":
            actions.append(VisualAction(kind="wait", duration_seconds=action.get("duration")))
        elif action_type == "screenshot":
            actions.append(VisualAction(kind="screenshot"))
    return actions


def normalize_provider_actions(provider: VisualProviderId, raw: dict[str, Any]) -> list[VisualAction]:
    if provider == "anthropic_computer_use":
        return _anthropic_actions(raw)
    if provider == "gemini_computer_use":
        return _gemini_actions(raw)
    if provider == "openai_computer_use":
        return _openai_actions(raw)
    return []
