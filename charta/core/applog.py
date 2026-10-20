"""File logging + a session file, so a closed console never loses the evidence.

`charta open` is usually launched from Explorer or a shortcut, where stderr dies
with the window. Everything that matters — startup, the port actually chosen,
server errors, the exit reason, and any traceback — is appended to
``<state_dir>/charta.log``. ``session.json`` lets the CLI find a running instance
and explain what happened if one vanished.

Never raises: a logging failure must not stop Charta from starting.
"""
from __future__ import annotations

import datetime
import json
import logging
import pathlib
import sys
import threading
import traceback
from typing import Any

from .config import AppConfig

LOG_NAME = "charta.log"
SESSION_NAME = "session.json"
_LOGGER_NAME = "charta"
_configured = False
_handler_path: pathlib.Path | None = None


class _SafeStreamHandler(logging.StreamHandler):
    """A stderr handler that survives having its stream closed underneath it.

    The file is the source of truth and must never be lost to a stderr that a
    test harness (or a GUI launcher with no console) closed or replaced, which
    is otherwise a real `logging` error at the worst possible moment.
    """

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        try:
            super().emit(record)
        except (OSError, ValueError):  # closed or detached stream
            pass


def log_path(cfg: AppConfig) -> pathlib.Path:
    return cfg.state_path() / LOG_NAME


def session_path(cfg: AppConfig) -> pathlib.Path:
    return cfg.state_path() / SESSION_NAME


def _timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _open_file_handler(path: pathlib.Path, logger: logging.Logger) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"charta: cannot write {path} ({e}); logging to stderr only", file=sys.stderr)
        return False
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return True


def _close_file_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


def setup(cfg: AppConfig, *, level: int = logging.INFO) -> pathlib.Path:
    """Point logging at this state dir, and capture uncaught exceptions once.

    Idempotent, but *not* once-only: the Electron shell, the CLI and the tests all
    call this with different state dirs, and a first call that pinned the handlers
    would silently report a log file it never opened (the file the caller is told
    to read would not exist).
    """
    global _configured, _handler_path
    path = log_path(cfg)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    if _handler_path != path:
        _close_file_handlers(logger)
        if not any(isinstance(h, _SafeStreamHandler) for h in logger.handlers):
            stderr = _SafeStreamHandler()
            stderr.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            logger.addHandler(stderr)
        _handler_path = path if _open_file_handler(path, logger) else None
    if not _configured:
        sys.excepthook = _log_exception
        threading.excepthook = _log_thread_exception
        _configured = True
    logger.info("--- charta %s on %s (python %s) ---", _version(), sys.platform,
                sys.version.split()[0])
    return path


def _log_exception(exc_type, exc, tb) -> None:
    _log_traceback("uncaught exception", exc_type, exc, tb)


def _log_thread_exception(args) -> None:
    _log_traceback(f"uncaught exception in thread {getattr(args.thread, 'name', '?')}",
                   args.exc_type, args.exc_value, args.exc_traceback)


def _log_traceback(label: str, exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        return
    logging.getLogger(_LOGGER_NAME).error("%s\n%s", label, "".join(traceback.format_exception(exc_type, exc, tb)))
    traceback.print_exception(exc_type, exc, tb, file=sys.stderr)


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def _version() -> str:
    try:
        from .. import __version__ as v

        return str(v)
    except Exception:  # noqa: BLE001
        return "?"


# --- session file --------------------------------------------------------
def write_session(cfg: AppConfig, **fields: Any) -> pathlib.Path:
    """Record the running instance (pid/port/url/mode) for later diagnosis."""
    path = session_path(cfg)
    payload = {"started": _timestamp(), **fields}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        get_logger("session").warning("could not write %s: %s", path, e)
    get_logger("session").info("session started: %s", payload)
    return path


def read_session(cfg: AppConfig) -> dict:
    try:
        return json.loads(session_path(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def session_running(cfg: AppConfig) -> bool:
    """True only if the recorded instance still answers on its port.

    A hard-killed process (or one killed by the Electron shell) leaves a stale
    session.json; the port probe keeps `charta logs` from claiming a ghost is
    alive.
    """
    import socket

    session = read_session(cfg)
    port = session.get("port")
    if not isinstance(port, int):
        return False
    host = str(session.get("host") or "127.0.0.1")
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def clear_session(cfg: AppConfig, reason: str = "") -> None:
    if reason:
        get_logger("session").info("session ended: %s", reason)
    try:
        session_path(cfg).unlink(missing_ok=True)
    except OSError:
        pass


def read_log(cfg: AppConfig, lines: int = 60) -> str:
    """Last ``lines`` of the log, for `charta logs` and failure messages."""
    try:
        content = log_path(cfg).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"(no log yet at {log_path(cfg)}: {e})"
    return "\n".join(content[-lines:]) if content else f"(log at {log_path(cfg)} is empty)"
