"""Native window host: a real window when pywebview is available, browser otherwise.

Charta's UI is a local web app; this is the thin native shell that gives it a
window, a taskbar entry, a dark title bar, Mica and remembered geometry.
pywebview is optional (see requirements.txt) — without it we open the default
browser and say so, so the app never hard-fails on a missing dependency.
"""
from __future__ import annotations

import inspect
import os
import pathlib
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from . import electron as electron_shell

from ..core import applog
from ..core.config import AppConfig
from .native_window import (APP_USER_MODEL_ID, ICON_PATH, WindowGeometry, load_geometry,
                            polish_window, save_geometry)

APP_TITLE = "Charta"
_SERVER_ERROR: dict[str, str] = {"detail": ""}


def free_port(host: str = "127.0.0.1") -> int:
    """An unused local port (used when the configured one is busy)."""
    with socket.socket() as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def port_is_free(host: str, port: int) -> bool:
    """True only when nothing is serving on this port *and* we can claim it.

    A bind test alone is not enough: SO_REUSEADDR lets a bind succeed against a
    socket that is bound but not yet listening, so a half-dead instance would
    look free and then collide with uvicorn. Probe for a listener first, then
    bind without SO_REUSEADDR so a real conflict stays visible.
    """
    with socket.socket() as probe:
        probe.settimeout(0.3)
        if probe.connect_ex((host, port)) == 0:
            return False
    with socket.socket() as binder:
        try:
            binder.bind((host, port))
            return True
        except OSError:
            return False


def choose_port(host: str, port: int) -> tuple[int, str]:
    """Keep the configured port when free, otherwise take another.

    A stale Charta still holding 8123 used to make the whole app exit after a
    short wait, which is exactly the "it closes by itself" symptom.
    """
    if port and port_is_free(host, port):
        return port, ""
    replacement = free_port(host)
    note = (f"port {port} is already in use" if port else "no port configured")
    return replacement, f"{note} — using {replacement} instead"


def backend_command(port: int, debug: bool = False) -> list[str]:
    """argv for the backend process (used by the Electron shell's spawner)."""
    argv = [sys.executable, "-m", "charta.cli", "serve", "--port", str(port)]
    if debug:
        argv.append("--debug")
    return argv


def _serve_in_thread(host: str, port: int, debug: bool) -> object:
    """Run uvicorn in a daemon thread so the GUI owns the main thread.

    A failure to bind used to vanish into uvicorn's stderr; it is recorded in
    ``_SERVER_ERROR`` so wait_ready can report the real reason.
    """
    if debug:
        os.environ["CHARTA_DEBUG"] = "1"
    import uvicorn

    config = uvicorn.Config("charta.web.app:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    def target() -> None:
        try:
            server.run()
        except Exception as e:  # noqa: BLE001 — surfaced by wait_ready
            _SERVER_ERROR["detail"] = f"{type(e).__name__}: {e}"
            applog.get_logger("server").error("uvicorn died: %s", _SERVER_ERROR["detail"])

    threading.Thread(target=target, daemon=True, name="charta-uvicorn").start()
    return server


def wait_ready(host: str, port: int, timeout: float = 20.0) -> bool:
    """Poll /api/health so the window never opens on a dead server."""
    deadline = time.time() + timeout
    url = f"http://{host}:{port}/api/health"
    while time.time() < deadline:
        if _SERVER_ERROR["detail"]:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status < 500:
                    return True
        except Exception:  # noqa: BLE001 — server still starting
            time.sleep(0.2)
    return False


def supported_kwargs(func: object, kwargs: dict) -> dict:
    """Drop kwargs a pywebview version doesn't know (it grew these over time).

    pywebview raises TypeError on unknown kwargs, so passing `maximized` or
    `background_color` to an older build would kill the window before it opens.
    """
    try:
        params = inspect.signature(func).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in params}


def window_kwargs(geo: WindowGeometry, title: str, url: str) -> dict:
    return {
        "title": title, "url": url,
        "width": geo.width, "height": geo.height,
        "x": None if geo.x < 0 else geo.x, "y": None if geo.y < 0 else geo.y,
        "min_size": (480, 360), "maximized": geo.maximized,
        "background_color": "#0B0D12",  # avoids a white flash before first paint
    }


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


def _keep_alive() -> int:
    """Block while the backend serves the UI (browser mode / Ctrl+C to stop)."""
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def run(cfg: AppConfig, folder: str = "", *, debug: bool | None = None,
        port: int | None = None, browser_only: bool = False) -> int:
    """Start the backend and show the UI in a native window (or the browser).

    Returns an exit code and always logs the reason it stopped: a console opened
    from Explorer disappears with any error message, so the log file is the only
    place the failure survives.
    """
    debug = cfg.debug if debug is None else debug
    log = applog.setup(cfg)
    chosen, note = choose_port(cfg.host, port or cfg.port)
    if note:
        print(f"charta: {note}")
    url = url_for(cfg.host, chosen, folder)
    logger = applog.get_logger("desktop")
    logger.info("open: host=%s port=%s folder=%r debug=%s browser_only=%s",
                cfg.host, chosen, folder, debug, browser_only)
    print(f"log: {applog.log_path(cfg)}")

    # The Electron shell is the real desktop app (custom title bar, tray, Mica),
    # so it wins when it is installed; pywebview and the browser are fallbacks.
    electron_app = None if browser_only else electron_shell.desktop_dir()
    electron_argv = (electron_shell.command(port=chosen, folder=folder, debug=debug,
                                            app=electron_app)
                     if electron_app else None)
    if electron_app and electron_argv is None:
        print(f"charta: the desktop shell is present but Electron is not installed — "
              f"{electron_shell.install_hint()}")
    view = "electron" if electron_argv else ("browser" if browser_only else _view_kind())
    applog.write_session(cfg, pid=os.getpid(), port=chosen, url=url, view=view, debug=debug)
    if view == "electron":
        # Electron starts and supervises its own backend, so do not start one here.
        return _run_electron(cfg, electron_app, chosen, folder, debug)
    _serve_in_thread(cfg.host, chosen, debug)
    if not wait_ready(cfg.host, chosen):
        reason = _SERVER_ERROR["detail"] or f"no response from {url}api/health"
        logger.error("backend did not start: %s", reason)
        print(f"Charta could not start: {reason}")
        print(applog.read_log(cfg, lines=15))
        applog.clear_session(cfg, "backend failed to start")
        return 1
    logger.info("backend ready on %s", url)

    if view == "browser":
        print("Charta is running. pywebview/Electron not in use, so this opens in your browser.")
        print("  native window:  pip install pywebview   (or: cd desktop && npm start)")
        print(f"  {url}")
        webbrowser.open(url)
        try:
            return _keep_alive()
        finally:
            applog.clear_session(cfg, "browser session ended")

    started = time.time()
    try:
        code = _run_window(cfg, url, debug)
    finally:
        applog.clear_session(cfg, f"window closed after {time.time() - started:.1f}s")
    # A GUI that returns instantly means it failed to come up (missing WebView2,
    # no display). Fall back to the browser instead of exiting on the user.
    if time.time() - started < 2.0:
        logger.warning("window exited after %.1fs; falling back to the browser", time.time() - started)
        print("The native window closed immediately — falling back to your browser.")
        webbrowser.open(url)
        return _keep_alive()
    return code


def _view_kind() -> str:
    """pywebview gets the window only when Electron is not installed."""
    try:
        import webview  # noqa: F401

        return "window"
    except ImportError:
        return "browser"


def _run_electron(cfg: AppConfig, app: pathlib.Path | None, port: int,
                  folder: str, debug: bool) -> int:
    """Hand the UI to the Electron shell and stay alive as its launcher.

    Electron spawns the Python backend itself, so this only starts the window
    and reports why it stopped — the launcher's own exit used to be silent, and
    that was the "closes after a few seconds" symptom.
    """
    logger = applog.get_logger("desktop")
    argv = electron_shell.command(port=port, folder=folder, debug=debug, app=app)
    if argv is None:  # discovered a moment ago; treat as a normal fallback
        logger.warning("electron vanished between probe and launch")
        return 1
    print(f"Opening the Charta window: {' '.join(argv)}")
    logger.info("electron launch: %s", " ".join(argv))
    started = time.time()
    electron_log = applog.log_path(cfg).with_name("electron.log")
    child = electron_shell.launch(port=port, folder=folder, debug=debug, app=app,
                                  log_file=electron_log)
    if child is None:
        logger.error("electron could not be started")
        print(f"The Charta window could not be started. Log: {applog.log_path(cfg)}")
        return 1

    if wait_ready(cfg.host, port):
        logger.info("electron backend ready on http://%s:%s", cfg.host, port)
        print(f"Charta is running on http://{cfg.host}:{port}"
              "  (closing the window keeps it in the tray; Quit there to stop)")
        print(f"window log: {electron_log}")
    else:
        # Not fatal: a hop or a slow first start shows up in the shell's own log.
        logger.warning("no health response on %s while the Electron window is up", port)
        backend_log = applog.log_path(cfg).with_name("backend.log")
        print("The Charta window did not report a healthy backend."
              " Look at these logs for the reason:")
        print(f"  shell:   {electron_log}")
        print(f"  backend: {backend_log}")
        print(f"  app:     {applog.log_path(cfg)}")
        print("  tip: `charta testmodel` proves the model; `charta doctor` the rest.")
    applog.write_session(cfg, pid=child.pid, port=port, url=url_for(cfg.host, port, folder),
                         view="electron", debug=debug)
    try:
        while True:
            code = child.poll()
            if code is not None:
                elapsed = time.time() - started
                logger.info("electron exited with %s after %.1fs", code, elapsed)
                applog.clear_session(cfg, f"electron exited ({code})")
                if not health_ok(cfg.host, port):
                    # The shell exited and left no backend behind, so the user
                    # got no UI at all. Give them the browser on a fresh port
                    # instead of a dead one (the shell owned that backend).
                    logger.warning("electron exited with no live backend; browser fallback")
                    print("The Charta window closed before it was ready"
                          " — opening your browser instead.")
                    print(applog.read_log(cfg, lines=10))
                    return _browser_fallback(cfg, folder, debug)
                return code
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("launcher interrupted; the Charta window keeps running")
        print("Launcher stopped — the Charta window is still running (tray icon → Quit).")
        return 0


def health_ok(host: str, port: int, timeout: float = 1.5) -> bool:
    """One quick liveness probe (no wait loop)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as resp:
            return resp.status < 500
    except Exception:  # noqa: BLE001 — down is down
        return False


def _browser_fallback(cfg: AppConfig, folder: str, debug: bool) -> int:
    """Last resort: run the backend ourselves and open the browser on it.

    Best-effort: it starts a fresh backend on a free port and opens the browser
    whether or not the health check passes, because a dead browser tab is still
    closer to the UI than exiting with nothing.
    """
    port = free_port(cfg.host)
    url = url_for(cfg.host, port, folder)
    _serve_in_thread(cfg.host, port, debug)
    if not wait_ready(cfg.host, port, timeout=15.0):
        print("Charta's backend did not answer — run `charta doctor` for the reason.")
    applog.write_session(cfg, pid=os.getpid(), port=port, url=url, view="browser", debug=debug)
    print(f"Charta is running on {url}")
    webbrowser.open(url)
    try:
        return _keep_alive()
    finally:
        applog.clear_session(cfg, "browser fallback ended")


def _run_window(cfg: AppConfig, url: str, debug: bool) -> int:
    """pywebview path: the main thread owns the GUI loop."""
    import webview

    state_dir = cfg.state_path()
    geo = load_geometry(state_dir)
    kwargs = supported_kwargs(webview.create_window, window_kwargs(geo, APP_TITLE, url))
    try:
        window = webview.create_window(**kwargs)
    except TypeError as e:  # a build with a stricter signature than we detected
        applog.get_logger("desktop").warning("pywebview rejected options (%s); using defaults", e)
        window = webview.create_window(APP_TITLE, url, width=geo.width, height=geo.height)

    def on_loaded() -> None:
        handle = _hwnd(window)
        report = (polish_window(handle, mica=cfg.mica,
                                ico_path=ICON_PATH if ICON_PATH.exists() else None)
                  if handle else {"window_handle": False})
        applog.get_logger("desktop").info("native window polish: %s", report)
        print(f"native window polish: {report}")

    try:
        window.events.loaded += on_loaded
    except Exception as e:  # noqa: BLE001 — older pywebview builds
        applog.get_logger("desktop").warning("could not hook window.loaded: %s", e)
    save_geometry(state_dir, geo)  # ensure the file exists before the first move
    try:
        webview.start(debug=debug)
    finally:
        save_geometry(state_dir, _read_geometry(window, geo))
    return 0


def group_taskbar() -> bool:
    """Public helper so the CLI can group the taskbar entry before any window opens."""
    from .native_window import set_app_user_model_id

    return set_app_user_model_id(APP_USER_MODEL_ID)


__all__ = ["APP_TITLE", "backend_command", "choose_port", "free_port", "group_taskbar",
           "health_ok", "port_is_free", "run", "supported_kwargs", "url_for", "wait_ready",
           "window_kwargs"]
