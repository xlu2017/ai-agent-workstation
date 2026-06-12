from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ambient.config import AmbientCollectorConfig, get_ambient_config
from ambient.context_packet import build_context_packet
from ambient.collectors.browser_cdp import BrowserCdpCollector
from ambient.collectors.desktop_window import DesktopWindowCollector
from ambient.collectors.repo_watcher import RepoSnapshotCollector
from ambient.event_log import load_ambient_events, persist_many
from ambient.evidence_graph import write_evidence_graph
from ambient.legacy_context import collect_legacy_context_events
from ambient.reducers import reduce_ambient_events
from ambient.types import AmbientEvent, ContextPacket


@dataclass
class CollectorStatus:
    name: str
    enabled: bool
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectionResult:
    session_id: str
    events_collected: int
    events_persisted: int
    state_path: str | None
    context_packet_path: str | None
    statuses: list[CollectorStatus]
    context_packet: ContextPacket | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "events_collected": self.events_collected,
            "events_persisted": self.events_persisted,
            "state_path": self.state_path,
            "context_packet_path": self.context_packet_path,
            "statuses": [asdict(status) for status in self.statuses],
            "context_packet": self.context_packet.model_dump() if self.context_packet else None,
        }


class AmbientObservationService:
    """Session-scoped ambient observation orchestrator.

    This service is deliberately tolerant of server changes: each collector is
    optional, config is environment-backed, session metadata is read with
    fallbacks, and unavailable subsystems produce low-confidence status events
    instead of failing the entire collection pass.
    """

    def __init__(self, config: AmbientCollectorConfig | None = None):
        self.config = config or get_ambient_config()

    def collect_once(self, session_id: str, goal: str | None = None) -> CollectionResult:
        session_meta = self._load_session_meta(session_id)
        session_dir = self.config.sessions_dir / session_id
        repo_path = self._resolve_repo_path(session_meta)
        worktree_path = self._resolve_worktree_path(session_meta, repo_path)
        repo_id = self._repo_id(repo_path)
        branch = session_meta.get("branch") if isinstance(session_meta.get("branch"), str) else None
        statuses: list[CollectorStatus] = []
        events: list[AmbientEvent] = []

        if self.config.browser_enabled:
            try:
                browser = BrowserCdpCollector(self.config.browser_debug_urls)
                browser_events = browser.poll_tab_events(
                    session_id,
                    repo_id=repo_id,
                    worktree_id=str(worktree_path) if worktree_path else None,
                    branch=branch,
                    timeout=self.config.browser_timeout_seconds,
                )
                events.extend(browser_events)
                status_payload = browser_events[0].payload if browser_events else {}
                statuses.append(CollectorStatus("browser", True, "ok" if status_payload.get("available") else "degraded", details=status_payload))
            except Exception as exc:
                statuses.append(CollectorStatus("browser", True, "error", str(exc)[:240]))
        else:
            statuses.append(CollectorStatus("browser", False, "disabled"))

        if self.config.repo_enabled and worktree_path:
            try:
                repo_event = RepoSnapshotCollector(worktree_path).build_event(
                    session_id,
                    repo_id=repo_id,
                    worktree_id=str(worktree_path),
                )
                events.append(repo_event)
                statuses.append(CollectorStatus("repo", True, "ok" if repo_event.payload.get("available") else "degraded", details={"path": str(worktree_path)}))
            except Exception as exc:
                statuses.append(CollectorStatus("repo", True, "error", str(exc)[:240], {"path": str(worktree_path)}))
        elif self.config.repo_enabled:
            statuses.append(CollectorStatus("repo", True, "degraded", "No repo/worktree path could be resolved."))
        else:
            statuses.append(CollectorStatus("repo", False, "disabled"))

        if self.config.desktop_enabled:
            try:
                desktop_event = DesktopWindowCollector().collect(session_id)
                desktop_event.repo_id = repo_id
                desktop_event.worktree_id = str(worktree_path) if worktree_path else None
                desktop_event.branch = branch
                events.append(desktop_event)
                statuses.append(CollectorStatus("desktop", True, "ok" if desktop_event.payload.get("available") else "degraded", details=desktop_event.payload))
            except Exception as exc:
                statuses.append(CollectorStatus("desktop", True, "error", str(exc)[:240]))
        else:
            statuses.append(CollectorStatus("desktop", False, "disabled"))

        if self.config.legacy_context_enabled and session_dir.exists():
            try:
                legacy_events = collect_legacy_context_events(
                    session_id,
                    session_dir,
                    repo_id=repo_id,
                    worktree_id=str(worktree_path) if worktree_path else None,
                    branch=branch,
                )
                events.extend(legacy_events)
                statuses.append(CollectorStatus("legacy_context", True, "ok" if legacy_events else "idle", details={"event_count": len(legacy_events)}))
            except Exception as exc:
                statuses.append(CollectorStatus("legacy_context", True, "error", str(exc)[:240]))
        else:
            statuses.append(CollectorStatus("legacy_context", self.config.legacy_context_enabled, "disabled" if not self.config.legacy_context_enabled else "degraded"))

        events = events[: self.config.max_events_per_collect]
        persisted = persist_many(events, sessions_dir=self.config.sessions_dir) if events else []
        all_events = load_ambient_events(session_id, sessions_dir=self.config.sessions_dir)
        state = reduce_ambient_events(all_events)
        graph = write_evidence_graph(all_events, sessions_dir=self.config.sessions_dir)
        packet = build_context_packet(session_id=session_id, events=all_events, goal=goal)
        state_path, packet_path = self._write_reduced_outputs(session_id, state.model_dump(), packet.model_dump())
        return CollectionResult(
            session_id=session_id,
            events_collected=len(events),
            events_persisted=len(persisted),
            state_path=str(state_path) if state_path else None,
            context_packet_path=str(packet_path) if packet_path else None,
            statuses=statuses,
            context_packet=packet,
        )

    def health(self, session_id: str | None = None) -> dict[str, Any]:
        session_ids = [session_id] if session_id else self._list_session_ids()
        browser_health = BrowserCdpCollector(self.config.browser_debug_urls).list_targets(timeout=self.config.browser_timeout_seconds)[1]
        return {
            "ok": True,
            "config": {
                "sessions_dir": str(self.config.sessions_dir),
                "repos_dir": str(self.config.repos_dir),
                "browser_debug_urls": self.config.browser_debug_urls,
                "browser_enabled": self.config.browser_enabled,
                "desktop_enabled": self.config.desktop_enabled,
                "repo_enabled": self.config.repo_enabled,
                "legacy_context_enabled": self.config.legacy_context_enabled,
                "max_events_per_collect": self.config.max_events_per_collect,
            },
            "browser": browser_health,
            "sessions": session_ids,
        }

    def _load_session_meta(self, session_id: str) -> dict[str, Any]:
        path = self.config.sessions_dir / session_id / "session.json"
        if not path.exists():
            return {"id": session_id}
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"id": session_id}
        return data if isinstance(data, dict) else {"id": session_id}

    def _resolve_repo_path(self, meta: dict[str, Any]) -> Path | None:
        for key in ("worktree_path", "repo_path", "repo"):
            value = meta.get(key)
            if isinstance(value, str) and value:
                path = Path(value)
                if path.exists():
                    return path
        session_id = str(meta.get("id", ""))
        candidates = [
            self.config.repos_dir / f"worktree-{session_id}",
            self.config.repos_dir / session_id,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _resolve_worktree_path(self, meta: dict[str, Any], repo_path: Path | None) -> Path | None:
        value = meta.get("worktree_path")
        if isinstance(value, str) and value and Path(value).exists():
            return Path(value)
        return repo_path

    def _repo_id(self, repo_path: Path | None) -> str | None:
        if repo_path is None:
            return None
        return repo_path.name

    def _write_reduced_outputs(self, session_id: str, state: dict[str, Any], packet: dict[str, Any]) -> tuple[Path | None, Path | None]:
        ambient_dir = self.config.sessions_dir / session_id / "ambient"
        try:
            ambient_dir.mkdir(parents=True, exist_ok=True)
            state_path = ambient_dir / "state.json"
            packet_path = ambient_dir / "context_packet.json"
            self._atomic_write_json(state_path, state)
            self._atomic_write_json(packet_path, packet)
            return state_path, packet_path
        except OSError:
            return None, None

    def _atomic_write_json(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)

    def _list_session_ids(self) -> list[str]:
        if not self.config.sessions_dir.exists():
            return []
        ids = []
        for item in self.config.sessions_dir.iterdir():
            if item.is_dir() and (item / "session.json").exists():
                ids.append(item.name)
        return sorted(ids)
