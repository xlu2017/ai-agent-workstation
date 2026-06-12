from __future__ import annotations

import subprocess
from typing import Any

from ambient.types import AmbientEvent, AmbientEventType, AmbientSource


class DesktopWindowCollector:
    """Collect active window metadata without screenshots.

    On Linux/X11 desktops, xdotool is preferred and wmctrl/xprop provide useful
    fallback metadata. The collector degrades to low-confidence events when the
    desktop cannot be inspected.
    """

    def collect(self, session_id: str) -> AmbientEvent:
        payload, confidence = self._xdotool_payload()
        if not payload.get("available"):
            payload, confidence = self._wmctrl_payload()
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
            return {"available": False, "provider": "xdotool", "reason": "xdotool unavailable or no active X11 window"}, 0.2
        title = self._run(["xdotool", "getwindowname", window_id]).strip()
        pid = self._run(["xdotool", "getwindowpid", window_id]).strip()
        window_class = self._run(["xdotool", "getwindowclassname", window_id]).strip()
        xprop = self._xprop_payload(window_id)
        return {
            "available": True,
            "provider": "xdotool",
            "window_id": window_id,
            "window_title": title,
            "pid": pid,
            "window_class": window_class,
            "xprop": xprop,
        }, 0.9

    def _wmctrl_payload(self) -> tuple[dict[str, Any], float]:
        active_hex = self._run(["xprop", "-root", "_NET_ACTIVE_WINDOW"]).strip()
        active_id = ""
        if "#" in active_hex:
            active_id = active_hex.split("#", 1)[1].strip().split(",")[0].strip()
        listing = self._run(["wmctrl", "-lp"]).splitlines()
        active_row = None
        for row in listing:
            if active_id and row.lower().startswith(active_id.lower()):
                active_row = row
                break
        if not active_row and listing:
            active_row = listing[0]
        if not active_row:
            return {"available": False, "provider": "wmctrl", "reason": "wmctrl/xprop unavailable or no window list"}, 0.15
        parts = active_row.split(None, 4)
        return {
            "available": True,
            "provider": "wmctrl",
            "window_id": parts[0] if len(parts) > 0 else active_id,
            "desktop": parts[1] if len(parts) > 1 else "",
            "pid": parts[2] if len(parts) > 2 else "",
            "host": parts[3] if len(parts) > 3 else "",
            "window_title": parts[4] if len(parts) > 4 else "",
        }, 0.65

    def _xprop_payload(self, window_id: str) -> dict[str, str]:
        output = self._run(["xprop", "-id", window_id])
        result: dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("WM_CLASS") or line.startswith("WM_NAME") or line.startswith("_NET_WM_PID"):
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()[:300]
        return result

    def _run(self, command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout
