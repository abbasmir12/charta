"""File tools: read, edit and put aside — without ever destroying anything.

Charta never deletes a user's file. "Deleting" means moving the file to
``.charta/trash/`` where the user can see it and bring it back; editing means
writing a new version while keeping the previous one as ``.charta-old``. Both
actions are journalled and committed to the folder's history.
"""
from __future__ import annotations

import json
import pathlib
import shutil

from . import journal

TRASH_DIR = ".charta/trash"
MANIFEST = "manifest.json"
MAX_EDIT_BYTES = 2_000_000


class ToolError(Exception):
    """A tool call that could not be done (the UI shows the message)."""


def _root(folder: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(folder).resolve()


def resolve(folder: str | pathlib.Path, path: str, *, in_trash: bool = False) -> pathlib.Path:
    """Resolve a path inside the folder, refusing to escape it."""
    root = _root(folder)
    if not path:
        raise ToolError("No file given.")
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        raise ToolError("Charta only works on files inside the folder.")
    if ".charta" in target.parts and not in_trash:
        raise ToolError("That file belongs to Charta.")
    return target


def write(folder: str | pathlib.Path, path: str, text: str) -> dict:
    """Write a text file, keeping the previous version as ``<name>.charta-old``."""
    root = _root(folder)
    target = resolve(folder, path)
    if len(text.encode("utf-8", errors="ignore")) > MAX_EDIT_BYTES:
        raise ToolError("That is too large to edit in place.")
    backup = ""
    if target.exists():
        backup = str(target.with_name(target.name + ".charta-old").relative_to(root))
        shutil.copy2(str(target), str(target.with_name(target.name + ".charta-old")))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    journal.record(root, path, path, f"edited {path}")
    return {"path": str(target.relative_to(root)), "backup": backup,
            "bytes": len(text.encode("utf-8"))}


def _manifest_path(folder: pathlib.Path) -> pathlib.Path:
    return folder / TRASH_DIR / MANIFEST


def _read_manifest(folder: pathlib.Path) -> dict:
    p = _manifest_path(folder)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_manifest(folder: pathlib.Path, data: dict) -> None:
    p = _manifest_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def trash(folder: str | pathlib.Path, path: str) -> dict:
    """Move a file to ``.charta/trash/`` — it can be brought back."""
    root = _root(folder)
    target = resolve(folder, path)
    if not target.exists():
        raise ToolError("That file is not there.")
    trash_dir = root / TRASH_DIR
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / target.name
    i = 2
    while dest.exists():
        dest = trash_dir / f"{target.stem} ({i}){target.suffix}"
        i += 1
    rel_from = str(target.relative_to(root))
    shutil.move(str(target), str(dest))
    rel_to = str(dest.relative_to(root))
    manifest = _read_manifest(root)
    manifest[rel_to] = rel_from
    _write_manifest(root, manifest)
    journal.record(root, rel_from, rel_to, "moved to Charta's trash (not deleted)")
    return {"from": rel_from, "to": rel_to}


def restore(folder: str | pathlib.Path, path: str) -> dict:
    """Bring a file back from ``.charta/trash/`` to where it came from."""
    root = _root(folder)
    target = resolve(folder, path, in_trash=True)
    if not target.exists():
        raise ToolError("That file is not in the trash.")
    rel = str(target.relative_to(root))
    if TRASH_DIR not in rel:
        raise ToolError("That file is not in the trash.")
    manifest = _read_manifest(root)
    original = manifest.get(rel, target.name)
    dest = root / original
    if dest.exists():
        dest = root / f"{target.stem} (restored){target.suffix}"
    shutil.move(str(target), str(dest))
    manifest.pop(rel, None)
    _write_manifest(root, manifest)
    journal.record(root, rel, str(dest.relative_to(root)), "restored from Charta's trash")
    return {"restored": str(dest.relative_to(root))}


def trash_listing(folder: str | pathlib.Path) -> list[dict]:
    """What is currently in the folder's trash."""
    root = _root(folder)
    trash_dir = root / TRASH_DIR
    if not trash_dir.exists():
        return []
    manifest = _read_manifest(root)
    out = []
    for p in sorted(trash_dir.iterdir()):
        if p.is_file() and p.name != MANIFEST:
            rel = str(p.relative_to(root))
            out.append({"name": p.name, "path": rel, "size": p.stat().st_size,
                        "was": manifest.get(rel, "")})
    return out
