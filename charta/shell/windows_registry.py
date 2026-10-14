"""Windows Explorer right-click integration (HKCU, no admin)."""
from __future__ import annotations

import pathlib
import sys

KEYS = [
    r"Software\Classes\Directory\shell\Charta",
    r"Software\Classes\Directory\Background\shell\Charta",
]
ICON = pathlib.Path(__file__).resolve().parent.parent / "assets" / "charta.ico"


def _launcher() -> str:
    """Prefer the installed console script; fall back to `python -m charta.cli`."""
    guess = pathlib.Path(sys.executable).with_name("charta.exe")
    return str(guess) if guess.exists() else f'"{sys.executable}" -m charta.cli'


def install() -> str:
    if sys.platform != "win32":
        return "Shell integration is Windows-only; skipped on this OS (no-op)."
    import winreg

    launcher = _launcher()
    # Multi-size .ico so Explorer/taskbar pick a crisp size (see tools/make_icon.py).
    icon = str(ICON) if ICON.exists() else sys.executable
    for key in KEYS:
        param = '"%1"' if "Background" not in key else '"%V"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Watch with Charta")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
        # Opens the setup window for that folder (DESIGN.md screen 1) rather than
        # silently starting a console watcher. `charta watch` stays for the daemon.
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'{launcher} open {param}')
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
