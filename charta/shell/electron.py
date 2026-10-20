"""The Electron desktop shell, and how to reach it.

Charta's window is an Electron app (`desktop/`): it owns the native window, the
tray and the Python backend process. `charta open` — which is what Explorer's
"Watch with Charta" runs — prefers it, then falls back to pywebview, then to the
browser, so the entry point always shows something.

Nothing here changes files; it only decides *how* to show the UI. Discovery is
pure filesystem + PATH inspection so it is testable without a display.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPO_DESKTOP = REPO_ROOT / "desktop"

# Electron's own binary inside node_modules (the .bin shims are scripts, which
# CreateProcess cannot run directly on Windows, so the real binary wins).
_LOCAL_BINARIES = (
    "node_modules/electron/dist/electron.exe",
    "node_modules/electron/dist/electron",
)
# A packaged app (electron-builder output) places the executable here.
_PACKAGED_BINARIES = ("Charta.exe", "charta", "Charta")


def desktop_dir() -> pathlib.Path | None:
    """The Electron app directory, or None when the shell is not installed.

    Order: `CHARTA_DESKTOP` override, the repo checkout, then a per-user
    install location (Windows ``%LOCALAPPDATA%\\Programs\\Charta``), then
    ``/opt/charta`` on the rare system-wide install.
    """
    candidates: list[pathlib.Path] = []
    override = os.environ.get("CHARTA_DESKTOP")
    if override:
        candidates.append(pathlib.Path(override))
    candidates.append(REPO_DESKTOP)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(pathlib.Path(local) / "Programs" / "Charta")
    candidates.append(pathlib.Path("/opt/charta"))
    for candidate in candidates:
        if (candidate / "main.js").is_file():
            return candidate
    return None


def electron_bin(app: pathlib.Path) -> str | None:
    """The executable to start the shell with, or None when there is none."""
    for name in _PACKAGED_BINARIES:
        packaged = app / name
        if packaged.is_file():
            return str(packaged)
    for rel in _LOCAL_BINARIES:
        local = app / rel
        if local.is_file():
            return str(local)
    return None


def npx_bin() -> str | None:
    """`npx`, used only as a last resort when node_modules has no Electron.

    Without the marker check below this would happily download a 100 MB
    dependency at launch time, which is not something a right-click should do.
    """
    return shutil.which("npx") or shutil.which("npx.cmd")


def is_packaged(app: pathlib.Path, binary: str) -> bool:
    """True when ``binary`` is the app itself rather than an Electron runtime.

    A packaged app takes no script argument; `electron .` does.
    """
    return pathlib.Path(binary).parent == app


def command(port: int, folder: str = "", debug: bool = False,
            app: pathlib.Path | None = None, binary: str | None = None) -> list[str] | None:
    """argv that opens the Electron window, or None when Electron is unavailable.

    ``--port`` is passed through so the shell's backend binds the port Python
    already verified as free; ``--folder`` lands the setup window on the folder
    the user right-clicked.
    """
    app = app or desktop_dir()
    if app is None:
        return None
    resolved = binary or electron_bin(app)
    if resolved is None:
        npx = npx_bin()
        if npx is None:
            return None
        argv = [npx, "--no-install", "electron", "."]
    elif is_packaged(app, resolved):
        argv = [resolved]
    else:
        argv = [resolved, "."]
    argv.append(f"--port={port}")
    if folder:
        argv.append(f"--folder={folder}")
    if debug:
        argv.append("--debug")
    return argv


def available() -> bool:
    """True when `charta open` can hand the UI to the Electron shell."""
    return command(port=1) is not None


def launch(port: int, folder: str = "", debug: bool = False,
           app: pathlib.Path | None = None,
           log_file: pathlib.Path | None = None) -> subprocess.Popen | None:
    """Start the shell detached, so closing Charta's console cannot kill it.

    Electron starts and supervises its own backend, so the caller must not start
    one too; it waits for health on ``port`` and then just watches this process.

    Output goes to ``log_file`` rather than inheriting our stdio: the window
    outlives the launcher, and an inherited pipe would keep `charta open | head`
    (and any wrapper script) waiting forever for an EOF that never comes.
    """
    app = app or desktop_dir()
    if app is None:
        return None
    argv = command(port=port, folder=folder, debug=debug, app=app)
    if argv is None:
        return None
    kwargs: dict = {"cwd": str(app), "stdin": subprocess.DEVNULL}
    out = None
    try:
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            out = open(log_file, "a", encoding="utf-8", buffering=1)
            kwargs["stdout"] = kwargs["stderr"] = out
    except OSError:  # unwritable state dir: fall back to inheriting stdio
        out = None
    try:
        return _spawn(argv, kwargs)
    finally:
        if out is not None:
            out.close()  # the child keeps its own descriptor


def _spawn(argv: list[str], kwargs: dict) -> subprocess.Popen:
    if sys.platform == "win32":
        # Detached: the window is a GUI process, and Explorer's launcher exits.
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


__all__ = ["REPO_DESKTOP", "available", "command", "desktop_dir", "electron_bin",
           "is_packaged", "launch", "npx_bin"]
