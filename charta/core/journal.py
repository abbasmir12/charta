"""Undo journal (.charta/journal.jsonl). Every move logged, one-command undo."""
from __future__ import annotations

import datetime
import json
import pathlib
import shutil


def _path(folder: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(folder) / ".charta" / "journal.jsonl"


def record(folder: str | pathlib.Path, src: str, dst: str, reason: str) -> dict:
    p = _path(pathlib.Path(folder))
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
             "src": src, "dst": dst, "reason": reason}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def entries(folder: str | pathlib.Path) -> list[dict]:
    p = _path(pathlib.Path(folder))
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _move_back(folder: pathlib.Path, entry: dict) -> bool:
    src = pathlib.Path(entry["dst"])  # current location
    dst = pathlib.Path(entry["src"])  # original
    # resolve relative to folder
    if not src.is_absolute():
        src = folder / src
    if not dst.is_absolute():
        dst = folder / dst
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True


def undo_last(folder: str | pathlib.Path, dry_run: bool = False) -> dict | None:
    ents = entries(folder)
    if not ents:
        return None
    last = ents[-1]
    if dry_run:
        return last
    ok = _move_back(pathlib.Path(folder), last)
    # remove last line
    p = _path(pathlib.Path(folder))
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join(lines[:-1]) + ("\n" if len(lines) > 1 else ""), encoding="utf-8")
    last["undone"] = ok
    return last


def undo_since(folder: str | pathlib.Path, ts: str, dry_run: bool = False) -> int:
    ents = entries(folder)
    targets = [e for e in reversed(ents) if e.get("ts", "") >= ts]
    if dry_run:
        return len(targets)
    n = 0
    for _ in targets:
        if undo_last(folder):
            n += 1
    return n
