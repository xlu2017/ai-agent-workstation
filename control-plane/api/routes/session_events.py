"""Session event and timeline routes."""

import json
import re
from datetime import datetime

from fastapi import APIRouter

from api.config import SESSIONS_DIR

router = APIRouter(tags=["session-events"])

SECRET_PATS = [
    re.compile(r"\b(ghp_[A-Za-z0-9]{36,})\b"),
    re.compile(r"\b(gho_[A-Za-z0-9]{36,})\b"),
    re.compile(r"\b(glpat-[A-Za-z0-9\-]{20,})\b"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE),
    re.compile(r"\b(AKIA[A-Z0-9]{16})\b"),
    re.compile(r"tskey-[A-Za-z0-9\-]+"),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
]


def _redact(text: str) -> str:
    for pat in SECRET_PATS:
        text = pat.sub("[redacted]", text)
    return text


@router.get("/api/sessions/{session_id}/events")
def get_session_events(session_id: str, limit: int = 100):
    events_path = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    if not events_path.exists():
        return {"events": [], "total": 0}
    events = []
    for line in events_path.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"events": events[-limit:], "total": len(events)}


@router.get("/api/sessions/{session_id}/events/stream")
async def stream_session_events(session_id: str, after: int = 0):
    events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    events = []
    if events_file.exists():
        all_lines = events_file.read_text().strip().split("\n")
        for idx, line in enumerate(all_lines):
            if line.strip():
                try:
                    ev = json.loads(line)
                    seq = ev.get("sequence", idx + 1)
                    if seq > after:
                        ev["_seq"] = seq
                        events.append(ev)
                except Exception:
                    continue
    total = len(events) + after
    return {"events": events, "total": total}


@router.get("/api/sessions/{session_id}/timeline")
def get_timeline(session_id: str, limit: int = 100):
    session_dir = SESSIONS_DIR / session_id
    events_file = session_dir / "events" / "events.jsonl"

    events = []
    if events_file.exists():
        for line in events_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    summary = {
        "total_events": len(events),
        "tool_calls": sum(1 for e in events if e.get("type") == "tool_call"),
        "files_edited": len(set(
            e.get("args", {}).get("path", "")
            for e in events
            if e.get("type") == "tool_call" and e.get("tool") in ("write_file", "apply_patch") and e.get("success")
        )),
        "commands_run": sum(1 for e in events if e.get("type") == "tool_call" and e.get("tool") == "run_command"),
        "commits": sum(1 for e in events if e.get("type") == "tool_call" and e.get("tool") == "git_commit" and e.get("success")),
        "tasks_completed": sum(1 for e in events if e.get("type") == "task_complete"),
        "cost_usd": 0.0,
    }

    try:
        from timeline import Timeline
        tl = Timeline(session_id)
        old_summary = tl.get_summary()
        if old_summary.get("cost_usd"):
            summary["cost_usd"] = old_summary["cost_usd"]
    except Exception:
        pass

    return {"events": events[-limit:], "summary": summary}


@router.get("/api/v2/sessions/{session_id}/timeline")
def get_session_timeline_v2(session_id: str):
    session_dir = SESSIONS_DIR / session_id
    events_file = session_dir / "events" / "events.jsonl"

    raw_events = []
    if events_file.exists():
        for line in events_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    raw_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    started_at = raw_events[0].get("timestamp") if raw_events else None
    ended_at = raw_events[-1].get("timestamp") if raw_events else None
    start_ms = 0
    if started_at:
        try:
            start_ms = int(datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            start_ms = 0

    points = []
    desktop_active = False
    for ev in raw_events:
        ts = ev.get("timestamp", "")
        try:
            ev_ms = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ev_ms = start_ms
        offset_ms = ev_ms - start_ms

        ev_type = ev.get("event_type", ev.get("type", ""))
        data = ev.get("data", {})
        kind = "status"
        title = ev_type.replace("_", " ")
        prompt = None
        url = None

        if ev_type == "user_prompt_received":
            kind = "prompt"
            title = _redact(data.get("message", "User prompt"))[:120]
            prompt = title
        elif ev_type in ("action_started", "action_progress", "action_completed"):
            kind = "action"
            title = data.get("tool", title)
            if data.get("tool") == "browser_action":
                url = data.get("url")
                desktop_active = True
        elif ev_type in ("action_failed", "plan_validation_failed"):
            kind = "error"
            title = _redact(data.get("message", "Error"))[:100]
        elif ev_type in ("pr_created", "pr_merged"):
            kind = "pr"
            title = f"PR #{data.get('pr_number', '')}"
        elif ev_type in ("commit_created", "branch_pushed"):
            kind = "change"

        points.append({
            "id": ev.get("event_id", f"tp-{len(points)}"),
            "sessionId": session_id,
            "timestamp": ts,
            "offsetMs": offset_ms,
            "kind": kind,
            "title": _redact(title),
            "summary": _redact(data.get("args_summary", ""))[:100] if data.get("args_summary") else None,
            "url": url,
            "prompt": prompt,
            "desktopActive": desktop_active,
        })

    total_duration = points[-1]["offsetMs"] if points else 1
    seg_count = min(40, max(5, len(points) // 3 + 1))
    seg_dur = total_duration / seg_count if seg_count else 1

    segments = []
    for i in range(seg_count):
        s_start = i * seg_dur
        s_end = (i + 1) * seg_dur
        seg_pts = [p for p in points if s_start <= p["offsetMs"] < s_end]
        segments.append({
            "id": f"seg-{i}",
            "startOffsetMs": s_start,
            "endOffsetMs": s_end,
            "desktopActive": any(p["desktopActive"] for p in seg_pts),
            "eventCount": len(seg_pts),
        })

    return {
        "session_id": session_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": total_duration,
        "live": ended_at is None,
        "points": points,
        "segments": segments,
    }


@router.get("/api/sessions/{session_id}/timeline/summary")
def get_timeline_summary(session_id: str):
    from timeline import Timeline
    tl = Timeline(session_id)
    return tl.get_summary()


@router.get("/api/sessions/{session_id}/transcript")
async def session_transcript(session_id: str):
    from worklog.transcript import build_workflow_transcript

    events_file = SESSIONS_DIR / session_id / "events" / "events.jsonl"
    if not events_file.exists():
        return {"session_id": session_id, "headline": "", "items": [], "working_duration_ms": 0,
                "additions": 0, "deletions": 0, "tasks_created": 0,
                "validation": {"overall": "not_run", "commands": []}}

    raw_events = []
    for line in events_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                raw_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return build_workflow_transcript(session_id, raw_events)
