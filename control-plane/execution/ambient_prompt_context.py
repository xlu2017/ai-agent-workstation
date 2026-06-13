from __future__ import annotations

from pathlib import Path
from typing import Any

from ambient.context_packet import build_context_packet
from ambient.event_log import load_ambient_events
from ambient.types import ContextPacket


def load_ambient_context_packet(
    session_id: str,
    *,
    goal: str | None = None,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    limit: int = 500,
) -> ContextPacket | None:
    """Load the current ambient context packet for prompt/planner use.

    This is intentionally read-only. It does not collect new evidence and it does
    not grant file or command permissions. Callers must still perform runtime
    validation before inspecting files or mutating the worktree.
    """

    try:
        events = load_ambient_events(session_id, sessions_dir=sessions_dir, limit=limit)
    except Exception:
        return None
    if not events:
        return None
    return build_context_packet(session_id=session_id, events=events, goal=goal)


def ambient_packet_to_prompt_block(packet: ContextPacket | None, *, max_candidates: int = 8) -> str:
    """Format ambient evidence as a compact prompt block.

    The output is suitable for advisory planning or direct execution prompts. It
    preserves the boundary that ambient evidence is contextual, not authority.
    """

    if packet is None:
        return ""

    lines: list[str] = [
        "Ambient context evidence:",
        "- Treat this as contextual evidence only; validate paths and permissions before reading or editing files.",
    ]
    if packet.ambient_focus:
        kind = packet.ambient_focus.get("kind") or packet.ambient_focus.get("event_type") or "unknown"
        summary = packet.ambient_focus.get("summary") or packet.ambient_focus.get("label") or ""
        lines.append(f"- Current focus: {kind}{f' — {summary}' if summary else ''}")

    if packet.recent_observations:
        lines.append("- Recent observations:")
        for item in packet.recent_observations[-5:]:
            lines.append(f"  - {str(item)[:220]}")

    if packet.source_candidates:
        lines.append("- Ranked source candidates:")
        for candidate in packet.source_candidates[:max_candidates]:
            lines.append(f"  - {_format_source_candidate(candidate)}")
    elif packet.relevant_files:
        lines.append("- Relevant files:")
        for path in packet.relevant_files[:max_candidates]:
            lines.append(f"  - {path}")

    if packet.evidence_event_ids:
        lines.append("- Evidence event ids: " + ", ".join(packet.evidence_event_ids[-8:]))
    lines.append(f"- Aggregate confidence: {packet.confidence:.2f}")
    return "\n".join(lines)


def build_instruction_with_ambient_context(
    session_id: str,
    instruction: str,
    *,
    sessions_dir: str | Path = "/opt/workstation/sessions",
    limit: int = 500,
) -> tuple[str, dict[str, Any]]:
    """Return an instruction augmented with the latest ambient context.

    Metadata is returned separately for event logging and tests. If no ambient
    evidence exists, the original instruction is returned unchanged.
    """

    packet = load_ambient_context_packet(
        session_id,
        goal=instruction,
        sessions_dir=sessions_dir,
        limit=limit,
    )
    block = ambient_packet_to_prompt_block(packet)
    if not block:
        return instruction, {"ambient_context_attached": False}

    metadata = {
        "ambient_context_attached": True,
        "source_candidate_count": len(packet.source_candidates) if packet else 0,
        "relevant_file_count": len(packet.relevant_files) if packet else 0,
        "evidence_event_ids": packet.evidence_event_ids[-8:] if packet else [],
        "confidence": packet.confidence if packet else 0,
    }
    augmented = f"{instruction.rstrip()}\n\n{block}"
    return augmented, metadata


def ambient_packet_to_agent_core_context(packet: ContextPacket | None) -> dict[str, Any]:
    """Serialize ambient evidence for agent-core advisory APIs."""

    if packet is None:
        return {}
    return {
        "ambient_focus": packet.ambient_focus,
        "latest": packet.latest,
        "recent_observations": packet.recent_observations[-10:],
        "relevant_files": packet.relevant_files[:20],
        "source_candidates": packet.source_candidates[:12],
        "evidence_event_ids": packet.evidence_event_ids[-20:],
        "confidence": packet.confidence,
        "privacy": packet.privacy.model_dump(),
        "advisory_only": True,
        "requires_platform_validation": True,
    }


def _format_source_candidate(candidate: dict[str, Any]) -> str:
    path = candidate.get("path") or "unknown"
    line = f":{candidate.get('line')}" if candidate.get("line") else ""
    confidence = candidate.get("confidence", "n/a")
    symbol = f"; symbol={candidate.get('symbol')}" if candidate.get("symbol") else ""
    reason = f"; reason={candidate.get('reason')}" if candidate.get("reason") else ""
    return f"{path}{line}; confidence={confidence}{symbol}{reason}"
