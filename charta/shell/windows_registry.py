"""Windows Explorer right-click integration (HKCU, no admin)."""
from __future__ import annotations

import hashlib
import pathlib
import sys

from .native_window import ICON_PATH

KEYS = [
    r"Software\Classes\Directory\shell\Charta",
    r"Software\Classes\Directory\Background\shell\Charta",
]

# Per-folder verbs that Explorer only shows for folders Charta is watching, keyed
# by an AppliesTo (AQS) query matching that exact path. Prefix lets us find and
# clean up every marker we ever wrote.
DIR_SHELL = r"Software\Classes\Directory\shell"
WATCH_PREFIX = "ChartaWatched_"


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent.parent


def _launcher() -> str:
    """Command prefix for the shell entry, quoted and cwd-independent.

    Prefer a *windowless* interpreter: `charta.exe` is a console script, so
    launching it from Explorer flashes a black console window before the native
    UI appears. `pythonw.exe` (present next to any Windows interpreter, venv
    included) starts the same `open` command without a console. Without it,
    fall back to the installed console script, then to `python -c`.
    The payload uses no double quotes, which keeps `-c "..."` intact.
    """
    payload = (f"import sys;sys.path.insert(0,r'{_repo_root()}');"
               "from charta.cli import main;sys.exit(main())")
    windowless = pathlib.Path(sys.executable).with_name("pythonw.exe")
    if windowless.exists():
        return f'"{windowless}" -c "{payload}"'
    script = pathlib.Path(sys.executable).with_name("charta.exe")
    if script.exists():
        return f'"{script}"'
    return f'"{sys.executable}" -c "{payload}"'


def right_click_command(placeholder: str, launcher: str | None = None) -> str:
    """Build the HKCU command string. Pure string logic so it is testable anywhere.

    Loop variables (%1 for a folder, %V for the background) are quoted because
    every realistic Windows path contains spaces.
    """
    return f'{launcher or _launcher()} open "{placeholder}"'


def watched_query(folder: str | pathlib.Path) -> str:
    """AQS query that matches exactly this folder, for a watched verb's AppliesTo."""
    path = str(pathlib.Path(folder)).rstrip("\\/")
    return f'System.ItemPathDisplay:"{path}"'


def watched_verb(folder: str | pathlib.Path) -> str:
    """A stable, unique verb name so paths with spaces/punctuation stay valid keys."""
    digest = hashlib.sha1(str(pathlib.Path(folder)).casefold().encode("utf-8")).hexdigest()
    return f"{WATCH_PREFIX}{digest[:12]}"


def mark_watched(folder: str | pathlib.Path, launcher: str | None = None,
                 icon: str | None = None) -> str:
    """Register an Explorer verb that only appears on this watched folder.

    Returns the key written, or "" off Windows (the whole module is a guarded
    no-op there, same as the rest of the shell integration).
    """
    if sys.platform != "win32":
        return ""
    import winreg

    key = rf"{DIR_SHELL}\{watched_verb(folder)}"
    icon = icon or (str(ICON_PATH) if ICON_PATH.exists() else sys.executable)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Being watched with Charta")
        winreg.SetValueEx(k, "AppliesTo", 0, winreg.REG_SZ, watched_query(folder))
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, right_click_command("%1", launcher))
    return key


def unmark_watched(folder: str | pathlib.Path) -> None:
    """Remove a watched-folder verb (no-op off Windows)."""
    if sys.platform != "win32":
        return
    import winreg

    key = rf"{DIR_SHELL}\{watched_verb(folder)}"
    for sub in (key + r"\command", key):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass


def _watched_verbs() -> list[str]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DIR_SHELL) as root:
            names = []
            index = 0
            while True:
                try:
                    names.append(winreg.EnumKey(root, index))
                except OSError:
                    break
                index += 1
            return [n for n in names if n.startswith(WATCH_PREFIX)]
    except FileNotFoundError:
        return []


def sync_watched(folders: list[str]) -> int:
    """Make the Explorer markers match ``folders`` exactly (adds and removes)."""
    if sys.platform != "win32":
        return 0
    wanted = {watched_verb(f) for f in folders}
    for name in _watched_verbs():
        if name not in wanted:
            import winreg

            key = rf"{DIR_SHELL}\{name}"
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except FileNotFoundError:
                    pass
    for folder in folders:
        mark_watched(folder)
    return len(wanted)


def install() -> str:
    if sys.platform != "win32":
        return "Shell integration is Windows-only; skipped on this OS (no-op)."
    import winreg

    launcher = _launcher()
    # Multi-size .ico so Explorer/taskbar pick a crisp size (see tools/make_icon.py).
    icon = str(ICON_PATH) if ICON_PATH.exists() else sys.executable
    for key in KEYS:
        param = "%V" if "Background" in key else "%1"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Watch with Charta")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
        # Opens the setup window for that folder (DESIGN.md screen 1) rather than
        # silently starting a console watcher. `charta watch` stays for the daemon.
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, right_click_command(param, launcher))
    from ..core import watchlist
    from ..core.config import AppConfig

    sync_watched(watchlist.folders(AppConfig.load()))
    return "Installed: right-click a folder → 'Watch with Charta' (Win11: under 'Show more options')."


def uninstall() -> str:
    if sys.platform != "win32":
        return "Shell integration is Windows-only; nothing to remove here."
    import winreg

    for key in KEYS:
        for sub in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
    for name in _watched_verbs():
        key = rf"{DIR_SHELL}\{name}"
        for sub in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
    return "Uninstalled Charta shell entries."
