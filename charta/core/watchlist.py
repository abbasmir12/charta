"""Watched-folders registry: the folders Charta is responsible for.

Stored in the per-user state dir (never inside a watched folder), so it survives
the window closing and lets the UI, `charta status` and the tray agree on what is
being watched. One small JSON file; no database.

Every folder Charta has ever been given stays in the file with a ``watching``
flag, so unwatching keeps the record (and the folder's own ``.charta/`` state)
and re-watching resumes exactly where it left off.
"""
from __future__ import annotations

import datetime
import json
import pathlib

from .config import AppConfig

FILENAME = "watched.json"


def _path(cfg: AppConfig) -> pathlib.Path:
    return cfg.state_path() / FILENAME


def registry_path(cfg: AppConfig) -> pathlib.Path:
    """Where the registry lives (shown in Settings so users can find/edit it)."""
    return _path(cfg)


def _norm(folder: str | pathlib.Path) -> str:
    try:
        return str(pathlib.Path(folder).expanduser().resolve())
    except OSError:  # pragma: no cover - unreadable/odd paths
        return str(pathlib.Path(folder).expanduser())


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def load(cfg: AppConfig) -> list[dict]:
    """Every known folder, tolerating a corrupt or hand-edited file.

    Entries written by older versions have no ``watching`` key; they were all
    being watched, so they are treated as such.
    """
    p = _path(cfg)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict) or not e.get("folder"):
            continue
        entry = dict(e)
        entry.setdefault("watching", True)
        entry.setdefault("mode", "")
        entry.setdefault("added_at", "")
        entry.setdefault("unwatched_at", "")
        entry.setdefault("last_scan", "")
        out.append(entry)
    return out


def known(cfg: AppConfig) -> list[dict]:
    """Alias for :func:`load` — every folder Charta has ever been given."""
    return load(cfg)


def save(cfg: AppConfig, entries: list[dict]) -> pathlib.Path:
    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return p


def add(cfg: AppConfig, folder: str | pathlib.Path, mode: str = "") -> list[dict]:
    """Watch ``folder`` once. Adding an already-watched folder is a no-op."""
    folder = _norm(folder)
    entries = load(cfg)
    for e in entries:
        if e["folder"] == folder:
            if mode:
                e["mode"] = mode
            e["watching"] = True
            e["unwatched_at"] = ""
            save(cfg, entries)
            return entries
    entries.append({"folder": folder, "mode": mode, "watching": True,
                    "added_at": _now(), "unwatched_at": "", "last_scan": ""})
    save(cfg, entries)
    return entries


def remove(cfg: AppConfig, folder: str | pathlib.Path) -> list[str]:
    """Stop watching ``folder`` but keep the record (so it can be resumed).

    Returns the folders that are still being watched.
    """
    folder = _norm(folder)
    entries = load(cfg)
    for e in entries:
        if e["folder"] == folder:
            e["watching"] = False
            e["unwatched_at"] = _now()
    save(cfg, entries)
    return folders(cfg)


def is_watched(cfg: AppConfig, folder: str | pathlib.Path) -> bool:
    folder = _norm(folder)
    return any(e["folder"] == folder and e.get("watching", True) for e in load(cfg))


def folders(cfg: AppConfig) -> list[str]:
    """The folders currently being watched."""
    return [e["folder"] for e in load(cfg) if e.get("watching", True)]


def mark_scanned(cfg: AppConfig, folder: str | pathlib.Path) -> None:
    """Remember when a folder was last scanned (shown on the Folders page)."""
    folder = _norm(folder)
    entries = load(cfg)
    changed = False
    for e in entries:
        if e["folder"] == folder:
            e["last_scan"] = _now()
            changed = True
    if changed:
        save(cfg, entries)
