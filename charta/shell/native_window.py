"""Windows-native window polish, via ctypes.

Dark title bar (DwmSetWindowAttribute / DWMWA_USE_IMMERSIVE_DARK_MODE), Windows 11
Mica backdrop (DWMWA_SYSTEMBACKDROP_TYPE) with a solid caption-color fallback,
rounded corners, AppUserModelID for correct taskbar grouping, a multi-size .ico,
and remembered window geometry.

Everything here is a no-op off Windows so the core stays cross-platform and the
logic stays unit-testable on Linux/macOS. The visual effect needs Windows 11 and
a real window handle, which `charta open` obtains through pywebview when the
optional dependency is installed.
"""
from __future__ import annotations

import ctypes
import json
import pathlib
import sys
from dataclasses import asdict, dataclass

# --- DWM attribute ids (see dwmapi.h) ------------------------------------
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_SYSTEMBACKDROP_TYPE = 38

# --- DWMWA_SYSTEMBACKDROP_TYPE values ------------------------------------
BACKDROP_AUTO = 0
BACKDROP_NONE = 1
BACKDROP_MICA = 2
BACKDROP_ACRYLIC = 3
BACKDROP_TABBED = 4

DWMWCP_DEFAULT = 0
DWMWCP_ROUND = 2

APP_USER_MODEL_ID = "Charta.FolderWatcher"

# Design tokens (DESIGN.md): surface #12151C, text #E8EAF0 — COLORREF is 0x00BBGGRR.
CAPTION_COLOR_DARK = 0x001C1512
CAPTION_COLOR_LIGHT = 0x00FFFFFF
CAPTION_TEXT_DARK = 0x00F0EAE8
CAPTION_TEXT_LIGHT = 0x00241814


def is_windows() -> bool:
    return sys.platform == "win32"


def _dwm_set(hwnd: int, attribute: int, value: int) -> bool:
    """Set one int-valued DWM attribute. False on any failure (never raises)."""
    if not is_windows():
        return False
    try:
        handle = ctypes.c_void_p(int(hwnd))
        payload = ctypes.c_int(int(value))
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(  # type: ignore[attr-defined]
            handle, attribute, ctypes.byref(payload), ctypes.sizeof(payload))
        return result == 0
    except Exception:  # noqa: BLE001 — old Windows, no DWM, weird hwnd
        return False


def apply_dark_titlebar(hwnd: int, dark: bool = True) -> bool:
    """Match the title bar to the theme (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    return _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def apply_rounded_corners(hwnd: int) -> bool:
    return _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def apply_backdrop(hwnd: int, kind: int = BACKDROP_MICA, dark: bool = True) -> bool:
    """Windows 11 Mica; falls back to a solid caption color on Win10/old builds."""
    if _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, kind):
        return True
    return apply_solid_caption(hwnd, dark=dark)


def apply_solid_caption(hwnd: int, dark: bool = True) -> bool:
    """Fallback path: paint the title bar in our surface color instead of Mica."""
    ok_caption = _dwm_set(hwnd, DWMWA_CAPTION_COLOR,
                          CAPTION_COLOR_DARK if dark else CAPTION_COLOR_LIGHT)
    ok_text = _dwm_set(hwnd, DWMWA_TEXT_COLOR,
                       CAPTION_TEXT_DARK if dark else CAPTION_TEXT_LIGHT)
    return ok_caption or ok_text


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Group our windows under one taskbar entry (independent of python.exe)."""
    if not is_windows():
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False


def set_window_icon(hwnd: int, ico_path: str | pathlib.Path) -> bool:
    """Set a multi-size .ico on the window (title bar, alt-tab, taskbar)."""
    if not is_windows() or not pathlib.Path(ico_path).exists():
        return False
    try:
        IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x00000010, 0x00000040
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hicon = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 0, 0,
                                  LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not hicon:
            return False
        user32.SendMessageW(ctypes.c_void_p(int(hwnd)), WM_SETICON, ICON_SMALL, hicon)
        user32.SendMessageW(ctypes.c_void_p(int(hwnd)), WM_SETICON, ICON_BIG, hicon)
        return True
    except Exception:  # noqa: BLE001
        return False


def polish_window(hwnd: int, *, mica: bool = True, dark: bool = True,
                  ico_path: str | pathlib.Path | None = None) -> dict[str, bool]:
    """Apply the full native look. Returns a per-feature report (also logged to STATUS)."""
    report = {
        "dark_titlebar": apply_dark_titlebar(hwnd, dark),
        "rounded_corners": apply_rounded_corners(hwnd),
        "backdrop": apply_backdrop(hwnd, BACKDROP_MICA if mica else BACKDROP_NONE, dark),
        "app_user_model_id": set_app_user_model_id(),
        "icon": set_window_icon(hwnd, ico_path) if ico_path else False,
    }
    return report


# --- remembered geometry -------------------------------------------------
@dataclass
class WindowGeometry:
    x: int = -1
    y: int = -1
    width: int = 1180
    height: int = 780
    maximized: bool = False

    def is_usable(self) -> bool:
        """Guard against sizes that would land the window somewhere invisible."""
        return self.width >= 480 and self.height >= 360


def geometry_path(state_dir: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(state_dir).expanduser() / "window.json"


def load_geometry(state_dir: str | pathlib.Path) -> WindowGeometry:
    """Remembered size/position, or sensible defaults when missing/corrupt."""
    path = geometry_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        geo = WindowGeometry(
            x=int(data.get("x", -1)), y=int(data.get("y", -1)),
            width=int(data.get("width", 1180)), height=int(data.get("height", 780)),
            maximized=bool(data.get("maximized", False)),
        )
        return geo if geo.is_usable() else WindowGeometry()
    except (OSError, ValueError, TypeError):
        return WindowGeometry()


def save_geometry(state_dir: str | pathlib.Path, geo: WindowGeometry) -> pathlib.Path:
    """Persist geometry; never let a bad window kill the app on next launch."""
    path = geometry_path(state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(geo), indent=2), encoding="utf-8")
    except OSError:
        pass
    return path
