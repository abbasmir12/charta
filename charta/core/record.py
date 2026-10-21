"""Record what Charta did, in the folder's own private git history.

One place decides whether history is kept and what the commit message says, so
the CLI, the web UI and the watcher all leave the same trail.
"""
from __future__ import annotations

import pathlib

from . import history
from .config import AppConfig


def enabled(cfg: AppConfig | None = None) -> bool:
    """True when this folder can keep a history (git present, history on)."""
    if cfg is not None and not cfg.history:
        return False
    return history.available()


def record(cfg: AppConfig | None, folder: str | pathlib.Path, message: str) -> str | None:
    """Commit the folder's current state with a readable message."""
    if not enabled(cfg):
        return None
    return history.commit(folder, message)


def record_moves(cfg: AppConfig | None, folder: str | pathlib.Path,
                 moves: list[tuple[str, str, str]]) -> str | None:
    """Commit one or more moves: ``charta: moved 2 files — reason, reason``."""
    if not moves:
        return None
    if len(moves) == 1:
        src, dst, reason = moves[0]
        message = f"charta: moved {src} → {dst} — {reason}"
    else:
        reasons = "; ".join(dict.fromkeys(m for _, _, m in moves if m))
        message = f"charta: moved {len(moves)} files — {reasons}"
    return record(cfg, folder, message)


def record_index(cfg: AppConfig | None, folder: str | pathlib.Path,
                 files: int, proposals: int) -> str | None:
    """Commit after a scan: what was seen and what it proposed."""
    return record(cfg, folder,
                  f"charta: indexed {files} file{'s' if files != 1 else ''} — "
                  f"{proposals} proposal{'s' if proposals != 1 else ''}")


def record_outputs(cfg: AppConfig | None, folder: str | pathlib.Path,
                   kinds: list[str]) -> str | None:
    """Commit after the outputs were rebuilt."""
    if not kinds:
        return None
    return record(cfg, folder, f"charta: rebuilt outputs ({', '.join(kinds)})")


def record_undo(cfg: AppConfig | None, folder: str | pathlib.Path,
                src: str, dst: str) -> str | None:
    """Commit after a move was undone."""
    return record(cfg, folder, f"charta: undid the move {dst} → {src}")
