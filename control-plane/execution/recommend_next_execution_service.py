"""Recommend-next execution service scaffold.

Intent
------
This module is the future canonical boundary for interpreting any user-entered
session text. It intentionally contains no runtime wiring yet.

The service will call agent-core ``/actions/recommend-next`` and consume only the
four top-level decision types:

* ``execute``
* ``find_out_more``
* ``ask_user``
* ``stop``

Granular platform behavior must be decided after this boundary by the
workstation controller code (this repository). For example:

* missing repo context is handled as ``stop`` at this controller level
* creating or routing a session is handled as ``execute`` at this controller
  level
* selecting the concrete session operation, work-session operation, repository
  lookup, or executor action happens only after the top-level decision type is
  known

Non-goals for this scaffold
---------------------------
This file must not yet:

* change existing session routing behavior
* start workflows
* call agent-core
* create sessions
* mutate worktrees
* emit production events

It exists only to document the intended seam so future implementation does not
restore competing routers that bypass recommend-next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RecommendNextDecisionType(str, Enum):
    """Top-level decision types returned by recommend-next.

    The controller boundary should stop here. More granular actions are platform
    decisions made after this type-level interpretation step.
    """

    EXECUTE = "execute"
    FIND_OUT_MORE = "find_out_more"
    ASK_USER = "ask_user"
    STOP = "stop"


@dataclass(frozen=True)
class RecommendNextControllerDecision:
    """Normalized controller-level interpretation result.

    ``decision_type`` is the only authoritative output of this scaffold. The
    optional metadata exists to preserve recommendation details for future
    dispatch, logging, and UI messages without making this module responsible
    for granular platform behavior.
    """

    decision_type: RecommendNextDecisionType
    reason: str = ""
    source: str = "recommend_next"
    metadata: dict[str, Any] = field(default_factory=dict)


class RecommendNextExecutionService:
    """Scaffold for the canonical next-action interpretation service.

    Future implementation notes:

    1. Every new session prompt and every existing session chat message should
       enter this service.
    2. This service should call agent-core recommend-next and normalize the
       result to exactly one ``RecommendNextDecisionType``.
    3. It should not decide whether ``execute`` means route a session, create a
       work item, start one executor action, or perform another granular
       platform operation. That dispatch belongs to the controller layer after
       this boundary.
    4. It should treat missing repo context as a ``stop`` decision at this
       layer. A later controller step may render an assistant message that asks
       the user to attach a repo.
    5. It should treat creating or routing sessions as ``execute`` at this
       layer. A later controller step chooses the exact session operation.
    """

    async def interpret_user_message(self, *_args: Any, **_kwargs: Any) -> RecommendNextControllerDecision:
        """Future entry point for user-entered chat text.

        This scaffold deliberately raises until the real implementation is
        wired, so importing the module cannot silently alter behavior.
        """

        raise NotImplementedError("RecommendNextExecutionService is scaffold-only; no runtime behavior is implemented yet.")
