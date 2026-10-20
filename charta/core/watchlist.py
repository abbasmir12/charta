"""Watched-folders registry: the folders Charta is responsible for.

Stored in the per-user state dir (never inside a watched folder), so it survives
the window closing and lets the UI, `charta status` and the tray agree on what is
being watched. One small JSON file; no database.
"""
from __future__ import annotations

import datetime
import json
import pathlib

from .config import AppConfig

FILENAME = "watched.json"


def _path(cfg: AppConfig) -> pathlib.Path:
    return cfg.state_path() / FILENAME


def _norm(folder: str | pathlib.Path) -> str:
    try:
        return str(pathlib.Path(folder).expanduser().resolve())
    except OSError:  # pragma: no cover - unreadable/odd paths
        return str(pathlib.Path(folder).expanduser())


def load(cfg: AppConfig) -> list[dict]:
    """Every watched entry, tolerating a corrupt or hand-edited file."""
    p = _path(cfg)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("folder")]


def save(cfg: AppConfig, entries: list[dict]) -> pathlib.Path:
    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return p


def add(cfg: AppConfig, folder: str | pathlib.Path, mode: str = "") -> list[dict]:
    """Watch ``folder`` once. Adding an already-watched folder is a no-op."""
    folder = _norm(folder)
    entries = load(cfg)
    if any(e["folder"] == folder for e in entries):
        return entries
    entries.append({"folder": folder, "mode": mode,
                    "added_at": datetime.datetime.now().isoformat(timespec="seconds")})
    save(cfg, entries)
    return entries


def remove(cfg: AppConfig, folder: str | pathlib.Path) -> list[dict]:
    folder = _norm(folder)
    entries = [e for e in load(cfg) if e["folder"] != folder]
    save(cfg, entries)
    return entries


def is_watched(cfg: AppConfig, folder: str | pathlib.Path) -> bool:
    folder = _norm(folder)
    return any(e["folder"] == folder for e in load(cfg))


def folders(cfg: AppConfig) -> list[str]:
    return [e["folder"] for e in load(cfg)]
