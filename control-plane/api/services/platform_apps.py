from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DISPLAY_ENV = {
    "DISPLAY": os.environ.get("DISPLAY", ":10"),
    "XAUTHORITY": os.environ.get("XAUTHORITY", "/home/agent/.Xauthority"),
}
DESKTOP_APP_DIRS = (Path("/usr/share/applications"), Path.home() / ".local/share/applications")
DESKTOP_FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")


@dataclass(frozen=True)
class DesktopEntry:
    path: str
    name: str
    generic_name: str
    categories: list[str]
    keywords: list[str]
    exec_command: str


@dataclass(frozen=True)
class ProcessMatch:
    pid: int
    command: str
    args: str


@dataclass(frozen=True)
class CanonicalApplication:
    id: str
    name: str
    description: str
    category: str
    popularity: int
    aliases: list[str]
    desktop_categories: list[str]
    keywords: list[str]
    command_candidates: list[str]
    fallback_commands: list[str]
    launch_prompt: str


@dataclass(frozen=True)
class ResolvedPlatformApplication:
    id: str
    name: str
    description: str
    category: str
    popularity: int
    aliases: list[str]
    desktop_categories: list[str]
    keywords: list[str]
    commands: list[str]
    fallback_commands: list[str]
    installed: bool
    running: bool
    confidence: str
    launch_command: str | None
    matched_commands: list[str]
    matched_desktop_files: list[str]
    matched_processes: list[dict[str, object]]
    matched_windows: list[str]
    launch_prompt: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["preferredCommands"] = payload.pop("commands")
        payload["fallbackCommands"] = payload.pop("fallback_commands")
        payload["desktopCategories"] = payload.pop("desktop_categories")
        payload["launchCommand"] = payload.pop("launch_command")
        payload["matchedCommands"] = payload.pop("matched_commands")
        payload["matchedDesktopFiles"] = payload.pop("matched_desktop_files")
        payload["matchedProcesses"] = payload.pop("matched_processes")
        payload["matchedWindows"] = payload.pop("matched_windows")
        payload["launchPrompt"] = payload.pop("launch_prompt")
        payload["launchMode"] = "desktop_control"
        return payload


POPULAR_APP_DEFINITIONS: tuple[CanonicalApplication, ...] = (
    CanonicalApplication(
        id="terminal",
        name="Terminal",
        description="Interactive shell on the visible desktop.",
        category="System",
        popularity=100,
        aliases=["terminal", "shell", "console", "command line", "cli"],
        desktop_categories=["TerminalEmulator", "System", "Utility"],
        keywords=["terminal", "shell", "bash", "command", "console", "xterm"],
        command_candidates=[
            "xfce4-terminal", "gnome-terminal", "konsole", "mate-terminal", "lxterminal",
            "tilix", "terminator", "kgx", "foot", "alacritty", "kitty", "xterm",
        ],
        fallback_commands=["x-terminal-emulator"],
        launch_prompt="Open a terminal on the remote desktop.",
    ),
    CanonicalApplication(
        id="browser",
        name="Web Browser",
        description="Default graphical web browser.",
        category="Web",
        popularity=96,
        aliases=["browser", "web", "internet", "web browser"],
        desktop_categories=["WebBrowser", "Network"],
        keywords=["browser", "web", "chrome", "chromium", "firefox", "internet"],
        command_candidates=[
            "firefox", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "brave-browser", "microsoft-edge", "vivaldi", "opera", "epiphany",
        ],
        fallback_commands=["x-www-browser", "sensible-browser", "xdg-open"],
        launch_prompt="Open the web browser on the remote desktop.",
    ),
    CanonicalApplication(
        id="file-manager",
        name="File Manager",
        description="Visual filesystem browser for repositories and workstation files.",
        category="System",
        popularity=94,
        aliases=["files", "file manager", "folder", "folders", "explorer"],
        desktop_categories=["FileManager", "Utility", "System"],
        keywords=["files", "file manager", "folder", "directory", "thunar", "nautilus"],
        command_candidates=["thunar", "nautilus", "dolphin", "nemo", "pcmanfm", "caja"],
        fallback_commands=["xdg-open"],
        launch_prompt="Open the file manager at /opt/workstation/repos on the remote desktop.",
    ),
    CanonicalApplication(
        id="code-editor",
        name="Code Editor",
        description="Graphical code editor for repository work.",
        category="Development",
        popularity=88,
        aliases=["code", "editor", "ide", "vscode", "visual studio code", "cursor", "zed"],
        desktop_categories=["Development", "IDE", "TextEditor"],
        keywords=["code", "editor", "vscode", "visual studio code", "cursor", "zed", "ide"],
        command_candidates=["code", "codium", "code-oss", "cursor", "zed", "subl", "geany", "kate", "gedit"],
        fallback_commands=["editor", "xdg-open"],
        launch_prompt="Open the graphical code editor on the remote desktop.",
    ),
    CanonicalApplication(
        id="system-monitor",
        name="System Monitor",
        description="CPU, memory, and process monitor.",
        category="System",
        popularity=76,
        aliases=["system monitor", "task manager", "process monitor", "processes"],
        desktop_categories=["System", "Monitor"],
        keywords=["system monitor", "processes", "cpu", "memory", "task manager"],
        command_candidates=["xfce4-taskmanager", "gnome-system-monitor", "ksysguard", "plasma-systemmonitor", "mate-system-monitor", "lxtask", "htop"],
        fallback_commands=["top"],
        launch_prompt="Open the system monitor on the remote desktop.",
    ),
    CanonicalApplication(
        id="screenshot",
        name="Screenshot Tool",
        description="Desktop screenshot and screen-capture utility.",
        category="Utilities",
        popularity=72,
        aliases=["screenshot", "screen capture", "capture", "snipping"],
        desktop_categories=["Graphics", "Utility"],
        keywords=["screenshot", "screen capture", "image capture"],
        command_candidates=["xfce4-screenshooter", "gnome-screenshot", "spectacle", "flameshot", "mate-screenshot"],
        fallback_commands=[],
        launch_prompt="Open the screenshot tool on the remote desktop.",
    ),
    CanonicalApplication(
        id="settings",
        name="Settings",
        description="Desktop preferences, display, keyboard, and mouse configuration.",
        category="System",
        popularity=68,
        aliases=["settings", "preferences", "control center", "display settings"],
        desktop_categories=["Settings", "DesktopSettings", "System"],
        keywords=["settings", "preferences", "display", "keyboard", "mouse"],
        command_candidates=["xfce4-settings-manager", "gnome-control-center", "systemsettings", "mate-control-center", "lxqt-config"],
        fallback_commands=[],
        launch_prompt="Open desktop settings on the remote desktop.",
    ),
)


def _normalize_exec_command(value: str) -> str:
    cleaned = DESKTOP_FIELD_CODES.sub("", value).strip()
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        parts = cleaned.split()
    if not parts:
        return ""
    return Path(parts[0]).name


def _split_desktop_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _parse_desktop_file(path: Path) -> DesktopEntry | None:
    fields: dict[str, str] = {}
    in_desktop_entry = False
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return None

    for line in lines:
        stripped = line.strip()
        if stripped == "[Desktop Entry]":
            in_desktop_entry = True
            continue
        if stripped.startswith("[") and stripped.endswith("]") and stripped != "[Desktop Entry]":
            in_desktop_entry = False
        if not in_desktop_entry or not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        fields.setdefault(key, value)

    if fields.get("NoDisplay", "false").lower() == "true" or fields.get("Hidden", "false").lower() == "true":
        return None

    exec_command = _normalize_exec_command(fields.get("Exec", ""))
    if not exec_command:
        return None

    return DesktopEntry(
        path=str(path),
        name=fields.get("Name", path.stem),
        generic_name=fields.get("GenericName", ""),
        categories=_split_desktop_list(fields.get("Categories", "")),
        keywords=_split_desktop_list(fields.get("Keywords", "")),
        exec_command=exec_command,
    )


def _desktop_entries() -> list[DesktopEntry]:
    entries: list[DesktopEntry] = []
    for directory in DESKTOP_APP_DIRS:
        if not directory.exists():
            continue
        for desktop_file in directory.glob("*.desktop"):
            entry = _parse_desktop_file(desktop_file)
            if entry:
                entries.append(entry)
    return entries


def _command_matches(commands: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for command in commands:
        if shutil.which(command) and command not in matches:
            matches.append(command)
    return matches


def _entry_matches_app(entry: DesktopEntry, app: CanonicalApplication) -> bool:
    command_set = {*app.command_candidates, *app.fallback_commands}
    if entry.exec_command in command_set:
        return True
    categories = {category.lower() for category in entry.categories}
    if any(category.lower() in categories for category in app.desktop_categories):
        return True
    haystack = " ".join([entry.name, entry.generic_name, *entry.keywords, *entry.categories, entry.exec_command]).lower()
    return any(alias.lower() in haystack for alias in app.aliases)


def _process_rows() -> list[ProcessMatch]:
    try:
        result = subprocess.run(["ps", "-eo", "pid=,comm=,args="], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[ProcessMatch] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        rows.append(ProcessMatch(pid=int(parts[0]), command=parts[1], args=parts[2] if len(parts) > 2 else parts[1]))
    return rows


def _window_rows() -> list[str]:
    if not shutil.which("wmctrl"):
        return []
    try:
        result = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True, timeout=2, env={**os.environ, **DISPLAY_ENV})
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _process_matches(app: CanonicalApplication, commands: Iterable[str], rows: list[ProcessMatch]) -> list[ProcessMatch]:
    names = {Path(command).name.lower() for command in [*app.command_candidates, *app.fallback_commands, *commands]}
    aliases = {alias.lower() for alias in app.aliases}
    matches: list[ProcessMatch] = []
    for row in rows:
        command = Path(row.command).name.lower()
        args = row.args.lower()
        if command in names or any(alias in args for alias in aliases):
            matches.append(row)
    return matches[:10]


def _window_matches(app: CanonicalApplication, rows: list[str]) -> list[str]:
    terms = [app.id.lower(), app.name.lower(), *[alias.lower() for alias in app.aliases], *[command.lower() for command in app.command_candidates]]
    return [row for row in rows if any(term in row.lower() for term in terms)][:10]


def _resolve_app(app: CanonicalApplication, entries: list[DesktopEntry], processes: list[ProcessMatch], windows: list[str]) -> ResolvedPlatformApplication:
    matched_commands = _command_matches([*app.command_candidates, *app.fallback_commands])
    matched_desktop_entries = [entry for entry in entries if _entry_matches_app(entry, app)]
    desktop_exec_matches = [entry.exec_command for entry in matched_desktop_entries if entry.exec_command in [*app.command_candidates, *app.fallback_commands]]
    all_command_matches = list(dict.fromkeys([*matched_commands, *desktop_exec_matches]))
    matched_processes = _process_matches(app, all_command_matches, processes)
    matched_windows = _window_matches(app, windows)
    running = bool(matched_processes or matched_windows)
    installed = bool(all_command_matches or matched_desktop_entries)
    confidence = "running" if running else "installed" if installed else "catalog_only"
    launch_command = all_command_matches[0] if all_command_matches else None

    return ResolvedPlatformApplication(
        id=app.id,
        name=app.name,
        description=app.description,
        category=app.category,
        popularity=app.popularity,
        aliases=app.aliases,
        desktop_categories=app.desktop_categories,
        keywords=app.keywords,
        commands=app.command_candidates,
        fallback_commands=app.fallback_commands,
        installed=installed,
        running=running,
        confidence=confidence,
        launch_command=launch_command,
        matched_commands=all_command_matches,
        matched_desktop_files=[entry.path for entry in matched_desktop_entries],
        matched_processes=[asdict(row) for row in matched_processes],
        matched_windows=matched_windows,
        launch_prompt=app.launch_prompt,
    )


def _score(app: ResolvedPlatformApplication, query: str) -> int:
    q = query.strip().lower()
    haystack = " ".join([
        app.name, app.description, app.category, *app.aliases, *app.keywords,
        *app.desktop_categories, *app.commands, *app.fallback_commands, *app.matched_commands,
    ]).lower()
    value = app.popularity + (80 if app.running else 0) + (40 if app.installed else 0)
    if q:
        if q in app.name.lower():
            value += 120
        if any(q in alias.lower() for alias in app.aliases):
            value += 100
        if any(q in keyword.lower() for keyword in app.keywords):
            value += 80
        if q in haystack:
            value += 40
        else:
            value -= 200
    return value


def resolve_popular_applications(query: str = "") -> list[ResolvedPlatformApplication]:
    entries = _desktop_entries()
    processes = _process_rows()
    windows = _window_rows()
    resolved = [_resolve_app(app, entries, processes, windows) for app in POPULAR_APP_DEFINITIONS]
    return [app for app in sorted(resolved, key=lambda item: _score(item, query), reverse=True) if _score(app, query) > -100]


def discover_popular_applications(query: str = "") -> list[dict[str, object]]:
    return [app.to_dict() for app in resolve_popular_applications(query)]


def launch_popular_application(app_id: str) -> dict[str, object]:
    apps = resolve_popular_applications()
    app = next((candidate for candidate in apps if candidate.id == app_id), None)
    if app is None:
        return {"opened": False, "error": f"Unknown application: {app_id}"}
    if not app.launch_command:
        return {"opened": False, "error": f"No allowlisted launch command is installed for {app.name}", "application": app.to_dict()}

    env = {**os.environ, **DISPLAY_ENV}
    subprocess.Popen([app.launch_command], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"opened": True, "application": app.to_dict(), "command": app.launch_command}
