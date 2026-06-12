from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

DISPLAY_ENV = {
    "DISPLAY": os.environ.get("DISPLAY", ":10"),
    "XAUTHORITY": os.environ.get("XAUTHORITY", "/home/agent/.Xauthority"),
}


@dataclass(frozen=True)
class PlatformApplication:
    id: str
    name: str
    description: str
    category: str
    popularity: int
    keywords: list[str]
    commands: list[str]
    installed: bool
    launch_prompt: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["preferredCommands"] = payload.pop("commands")
        payload["launchPrompt"] = payload.pop("launch_prompt")
        payload["launchMode"] = "desktop_control"
        return payload


POPULAR_APP_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "id": "terminal",
        "name": "Terminal",
        "description": "Interactive shell on the visible desktop.",
        "category": "System",
        "popularity": 100,
        "keywords": ["terminal", "shell", "bash", "command", "console", "xterm"],
        "commands": ["xfce4-terminal", "x-terminal-emulator", "xterm"],
        "launch_prompt": "Open a terminal on the remote desktop.",
    },
    {
        "id": "browser",
        "name": "Web Browser",
        "description": "Default graphical web browser.",
        "category": "Web",
        "popularity": 96,
        "keywords": ["browser", "web", "chrome", "chromium", "firefox", "internet"],
        "commands": ["google-chrome", "chromium", "chromium-browser", "firefox", "xdg-open"],
        "launch_prompt": "Open the web browser on the remote desktop.",
    },
    {
        "id": "file-manager",
        "name": "File Manager",
        "description": "Visual filesystem browser for repositories and workstation files.",
        "category": "System",
        "popularity": 94,
        "keywords": ["files", "file manager", "folder", "directory", "thunar", "nautilus"],
        "commands": ["thunar", "nautilus", "xdg-open"],
        "launch_prompt": "Open the file manager at /opt/workstation/repos on the remote desktop.",
    },
    {
        "id": "code-editor",
        "name": "Code Editor",
        "description": "Graphical code editor for repository work.",
        "category": "Development",
        "popularity": 88,
        "keywords": ["code", "editor", "vscode", "visual studio code", "cursor", "zed"],
        "commands": ["code", "codium", "cursor", "zed"],
        "launch_prompt": "Open the graphical code editor on the remote desktop.",
    },
    {
        "id": "system-monitor",
        "name": "System Monitor",
        "description": "CPU, memory, and process monitor.",
        "category": "System",
        "popularity": 76,
        "keywords": ["system monitor", "processes", "cpu", "memory", "task manager"],
        "commands": ["xfce4-taskmanager", "gnome-system-monitor", "htop"],
        "launch_prompt": "Open the system monitor on the remote desktop.",
    },
    {
        "id": "screenshot",
        "name": "Screenshot Tool",
        "description": "Desktop screenshot and screen-capture utility.",
        "category": "Utilities",
        "popularity": 72,
        "keywords": ["screenshot", "screen capture", "image capture"],
        "commands": ["xfce4-screenshooter", "gnome-screenshot"],
        "launch_prompt": "Open the screenshot tool on the remote desktop.",
    },
    {
        "id": "settings",
        "name": "Settings",
        "description": "Desktop preferences, display, keyboard, and mouse configuration.",
        "category": "System",
        "popularity": 68,
        "keywords": ["settings", "preferences", "display", "keyboard", "mouse"],
        "commands": ["xfce4-settings-manager", "gnome-control-center"],
        "launch_prompt": "Open desktop settings on the remote desktop.",
    },
)


def _desktop_commands() -> set[str]:
    commands: set[str] = set()
    desktop_dirs = [Path("/usr/share/applications"), Path.home() / ".local/share/applications"]
    for directory in desktop_dirs:
        if not directory.exists():
            continue
        for desktop_file in directory.glob("*.desktop"):
            try:
                for line in desktop_file.read_text(errors="ignore").splitlines():
                    if not line.startswith("Exec="):
                        continue
                    command = line.split("=", 1)[1].strip().split()[0]
                    if command:
                        commands.add(Path(command).name)
                    break
            except OSError:
                continue
    return commands


def _is_installed(commands: Iterable[str], desktop_commands: set[str] | None = None) -> bool:
    desktop_commands = desktop_commands or _desktop_commands()
    return any(shutil.which(command) or command in desktop_commands for command in commands)


def _materialize(definition: dict[str, object], desktop_commands: set[str] | None = None) -> PlatformApplication:
    commands = list(definition["commands"])  # type: ignore[index]
    return PlatformApplication(
        id=str(definition["id"]),
        name=str(definition["name"]),
        description=str(definition["description"]),
        category=str(definition["category"]),
        popularity=int(definition["popularity"]),
        keywords=list(definition["keywords"]),  # type: ignore[arg-type,index]
        commands=commands,
        installed=_is_installed(commands, desktop_commands),
        launch_prompt=str(definition["launch_prompt"]),
    )


def discover_popular_applications(query: str = "") -> list[dict[str, object]]:
    desktop_commands = _desktop_commands()
    q = query.strip().lower()
    applications = [_materialize(definition, desktop_commands) for definition in POPULAR_APP_DEFINITIONS]

    def score(app: PlatformApplication) -> int:
        haystack = " ".join([app.name, app.description, app.category, *app.keywords, *app.commands]).lower()
        value = app.popularity + (40 if app.installed else 0)
        if q:
            if q in app.name.lower():
                value += 120
            if any(q in keyword.lower() for keyword in app.keywords):
                value += 80
            if q in haystack:
                value += 40
            else:
                value -= 200
        return value

    return [app.to_dict() for app in sorted(applications, key=score, reverse=True) if score(app) > -100]


def launch_popular_application(app_id: str) -> dict[str, object]:
    applications = [_materialize(definition) for definition in POPULAR_APP_DEFINITIONS]
    app = next((candidate for candidate in applications if candidate.id == app_id), None)
    if app is None:
        return {"opened": False, "error": f"Unknown application: {app_id}"}

    command = next((candidate for candidate in app.commands if shutil.which(candidate)), None)
    if command is None:
        return {"opened": False, "error": f"No launch command is installed for {app.name}", "application": app.to_dict()}

    env = {**os.environ, **DISPLAY_ENV}
    subprocess.Popen([command], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"opened": True, "application": app.to_dict(), "command": command}
