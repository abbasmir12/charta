"""Windows Explorer right-click integration (HKCU, no admin)."""
from __future__ import annotations

import pathlib
import sys

from .native_window import ICON_PATH

KEYS = [
    r"Software\Classes\Directory\shell\Charta",
    r"Software\Classes\Directory\Background\shell\Charta",
]


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent.parent


def _launcher() -> str:
    """Command prefix for the shell entry, quoted and cwd-independent.

    Prefer the installed console script. Without it (plain `pip install -r
    requirements.txt`), `-m charta.cli` would only work if Explorer happened to
    start us inside the repo, so bootstrap the repo root on sys.path instead.
    The payload uses no double quotes, which keeps `-c "..."` intact.
    """
    script = pathlib.Path(sys.executable).with_name("charta.exe")
    if script.exists():
        return f'"{script}"'
    payload = (f"import sys;sys.path.insert(0,r'{_repo_root()}');"
               "from charta.cli import main;sys.exit(main())")
    return f'"{sys.executable}" -c "{payload}"'


def right_click_command(placeholder: str, launcher: str | None = None) -> str:
    """Build the HKCU command string. Pure string logic so it is testable anywhere.

    Loop variables (%1 for a folder, %V for the background) are quoted because
    every realistic Windows path contains spaces.
    """
    return f'{launcher or _launcher()} open "{placeholder}"'


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
    return "Uninstalled Charta shell entries."
