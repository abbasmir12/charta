"""Native window host: a real window when pywebview is available, browser otherwise.

Charta's UI is a local web app; this is the thin native shell that gives it a
window, a taskbar entry, a dark title bar, Mica and remembered geometry.
pywebview is optional (see requirements.txt) — without it we open the default
browser and say so, so the app never hard-fails on a missing dependency.
"""
from __future__ import annotations

import os
import pathlib
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from .native_window import (APP_USER_MODEL_ID, WindowGeometry, load_geometry,
                            polish_window, save_geometry)

ICON = pathlib.Path(__file__).resolve().parent.parent / "assets" / "charta.ico"
APP_TITLE = "Charta"


def _serve_in_thread(host: str, port: int, debug: bool) -> object:
    """Run uvicorn in a daemon thread so the GUI owns the main thread."""
    if debug:
        os.environ["CHARTA_DEBUG"] = "1"
    import uvicorn

    config = uvicorn.Config("charta.web.app:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="charta-uvicorn").start()
    return server


def wait_ready(host: str, port: int, timeout: float = 20.0) -> bool:
    """Poll /api/health so the window never opens on a dead server."""
    deadline = time.time() + timeout
    url = f"http://{host}:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status < 500:
                    return True
        except Exception:  # noqa: BLE001 — server still starting
            time.sleep(0.2)
    return False


def _hwnd(window: object) -> int:
    """Best-effort window handle across pywebview backends (0 when unknown)."""
    form = getattr(getattr(window, "gui", None), "window", None)
    for attr in ("Handle", "hwnd"):
        handle = getattr(form, attr, None)
        if handle is None:
            continue
        for cast in (lambda h: int(h.ToInt64()), int):
            try:
                return cast(handle)
            except Exception:  # noqa: BLE001
                continue
    return 0


def _read_geometry(window: object, fallback: WindowGeometry) -> WindowGeometry:
    def number(name: str, default: int) -> int:
        try:
            return int(getattr(window, name))
        except (TypeError, ValueError, AttributeError):
            return default

    geo = WindowGeometry(
        x=number("x", fallback.x), y=number("y", fallback.y),
        width=number("width", fallback.width), height=number("height", fallback.height),
        maximized=bool(getattr(window, "maximized", fallback.maximized)),
    )
    return geo if geo.is_usable() else fallback


def url_for(host: str, port: int, folder: str = "") -> str:
    base = f"http://{host}:{port}/"
    return base + ("?" + urllib.parse.urlencode({"folder": folder}) if folder else "")


def run(host: str, port: int, folder: str = "", *, debug: bool = False,
        state_dir: str | pathlib.Path | None = None, mica: bool = True) -> int:
    """Start the server and show it in a window (or the browser). Returns exit code."""
    if state_dir is None:
        from ..core.config import AppConfig

        state_dir = AppConfig.load().state_path()
    state_dir = pathlib.Path(state_dir)
    url = url_for(host, port, folder)
    _serve_in_thread(host, port, debug)
    if not wait_ready(host, port):
        print(f"Charta server did not come up at http://{host}:{port} — check the log above.")
        return 1

    try:
        import webview
    except ImportError:
        print("Charta is running. pywebview is not installed, so this opens in your browser.")
        print("  native window:  pip install pywebview")
        print(f"  {url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\\nStopped.")
        return 0

    geo = load_geometry(state_dir)
    window = webview.create_window(
        APP_TITLE, url, width=geo.width, height=geo.height,
        x=None if geo.x < 0 else geo.x, y=None if geo.y < 0 else geo.y,
        min_size=(480, 360), maximized=geo.maximized, background_color="#0B0D12",
    )

    def on_loaded() -> None:
        handle = _hwnd(window)
        report = (polish_window(handle, mica=mica, ico_path=ICON if ICON.exists() else None)
                  if handle else {"window_handle": False})
        print(f"native window polish: {report}")

    try:
        window.events.loaded += on_loaded
    except Exception:  # noqa: BLE001 — older pywebview builds
        pass
    save_geometry(state_dir, geo)  # ensure the file exists before the first move
    try:
        webview.start()
    finally:
        save_geometry(state_dir, _read_geometry(window, geo))
    return 0


def group_taskbar() -> bool:
    """Public helper so the CLI can group the taskbar entry before any window opens."""
    from .native_window import set_app_user_model_id

    return set_app_user_model_id(APP_USER_MODEL_ID)


__all__ = ["APP_TITLE", "group_taskbar", "run", "url_for", "wait_ready"]
