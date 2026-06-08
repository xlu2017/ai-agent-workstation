"""
Session types and models.

Session types:
  root_session    — initial user task
  child_session   — related task sharing repo/worktree/context lineage
  parallel_session — independent task, usually separate worktree or executor
  queued_session  — task waiting for resources or user approval

Persists: parent_session_id, root_session_id, repo_id, worktree_id,
          executor_id, status, active_plan_id, created_from_prompt_id
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SessionType(str, Enum):
    ROOT = "root_session"
    CHILD = "child_session"
    PARALLEL = "parallel_session"
    QUEUED = "queued_session"


class SessionStatus(str, Enum):
    CREATED = "created"
    CLAIMED = "claimed"
    PLANNING = "planning"
    EDITING = "editing"
    VALIDATING = "validating"
    COMMITTED = "committed"
    ANSWERED = "answered"
    FAILED = "failed"
    BLOCKED = "blocked"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: f"session-{uuid.uuid4().hex[:12]}")
    session_type: SessionType = SessionType.ROOT
    status: SessionStatus = SessionStatus.CREATED
    repo_id: str = ""
    worktree_id: str = ""
    executor_id: str = ""
    active_plan_id: str = ""
    created_from_prompt_id: str = ""
    parent_session_id: str = ""
    root_session_id: str = ""
    prompt: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["session_type"] = self.session_type.value
        d["status"] = self.status.value
        return d


class SessionStore:
    """Persists sessions to JSON files.

    Storage: <sessions_dir>/<session_id>/session-meta.json
    """

    def __init__(self, sessions_dir: str | Path = "/opt/workstation/sessions"):
        self.sessions_dir = Path(sessions_dir)

    def _meta_path(self, session_id: str) -> Path:
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "session-meta.json"

    def save(self, session: Session) -> Session:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._meta_path(session.session_id)
        path.write_text(json.dumps(session.to_dict(), indent=2))
        return session

    def get(self, session_id: str) -> Session | None:
        path = self._meta_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return Session(
                session_id=data.get("session_id", session_id),
                session_type=SessionType(data.get("session_type", "root_session")),
                status=SessionStatus(data.get("status", "created")),
                repo_id=data.get("repo_id", ""),
                worktree_id=data.get("worktree_id", ""),
                executor_id=data.get("executor_id", ""),
                active_plan_id=data.get("active_plan_id", ""),
                created_from_prompt_id=data.get("created_from_prompt_id", ""),
                parent_session_id=data.get("parent_session_id", ""),
                root_session_id=data.get("root_session_id", ""),
                prompt=data.get("prompt", ""),
                allowed_actions=data.get("allowed_actions", []),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
        except (json.JSONDecodeError, ValueError):
            return None

    def list_sessions(
        self,
        parent_id: str | None = None,
        status: SessionStatus | None = None,
        session_type: SessionType | None = None,
    ) -> list[Session]:
        sessions = []
        if not self.sessions_dir.exists():
            return sessions
        for d in sorted(self.sessions_dir.iterdir()):
            s = self.get(d.name)
            if s is None:
                continue
            if parent_id and s.parent_session_id != parent_id:
                continue
            if status and s.status != status:
                continue
            if session_type and s.session_type != session_type:
                continue
            sessions.append(s)
        return sessions

    def update_status(self, session_id: str, status: SessionStatus | str) -> Session | None:
        session = self.get(session_id)
        if session is None:
            return None
        if isinstance(status, str):
            status = SessionStatus(status)
        session.status = status
        return self.save(session)
