from __future__ import annotations

import subprocess
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


class DesktopWindowCollector:
    """Collect active window metadata without screenshots.

    On the current Linux/XFCE/xRDP server, `xdotool`, `wmctrl`, and `xprop` are
    the pragmatic first tools. This collector uses xdotool when present and
    degrades to low-confidence events when the desktop cannot be inspected.
    """

    def collect(self, session_id: str) -> AmbientEvent:
        payload, confidence = self._xdotool_payload()
        return AmbientEvent(
            event_type=AmbientEventType.DESKTOP_WINDOW_FOCUSED.value,
            session_id=session_id,
            source=AmbientSource.DESKTOP,
            confidence=confidence,
            payload=payload,
        )

    def _xdotool_payload(self) -> tuple[dict[str, Any], float]:
        window_id = self._run(["xdotool", "getactivewindow"]).strip()
        if not window_id:
            return {"available": False, "reason": "xdotool unavailable or no active X11 window"}, 0.2
        title = self._run(["xdotool", "getwindowname", window_id]).strip()
        pid = self._run(["xdotool", "getwindowpid", window_id]).strip()
        window_class = self._run(["xdotool", "getwindowclassname", window_id]).strip()
        return {
            "available": True,
            "window_id": window_id,
            "window_title": title,
            "pid": pid,
            "window_class": window_class,
        }, 0.85

    def _run(self, command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout
