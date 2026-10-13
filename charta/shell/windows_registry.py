"""Windows Explorer right-click integration (HKCU, no admin)."""
from __future__ import annotations

import sys

KEYS = [
    r"Software\Classes\Directory\shell\Charta",
    r"Software\Classes\Directory\Background\shell\Charta",
]


def install() -> str:
    if sys.platform != "win32":
        return "Shell integration is Windows-only; skipped on this OS (no-op)."
    import winreg

    exe = sys.executable.replace("python.exe", "charta.exe")
    for key in KEYS:
        param = '"%1"' if "Background" not in key else '"%V"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Watch with Charta")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, exe)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" watch {param}')
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
