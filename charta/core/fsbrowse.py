"""Directory listing for the custom folder picker.

Directories only — the picker never needs to show files, and not showing them
keeps the surface small. Protected locations stay *browsable* (so the user can
see where they are) but are flagged, which is what lets the UI show the friendly
"Charta won't watch this" screen instead of a generic error.
"""
from __future__ import annotations

import os
import pathlib
import string
import sys
from dataclasses import asdict, dataclass, field

from .paths import is_protected


@dataclass
class DirListing:
    path: str
    parent: str | None = None
    dirs: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    protected: bool = False
    exists: bool = True
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def home_dir() -> str:
    try:
        return str(pathlib.Path.home())
    except Exception:  # noqa: BLE001
        return os.path.abspath(os.sep)


def drive_roots() -> list[str]:
    """Windows: existing drive letters. Elsewhere: just the filesystem root."""
    if sys.platform != "win32":
        return [os.sep]
    return [f"{letter}:\\" for letter in string.ascii_uppercase
            if pathlib.Path(f"{letter}:\\").exists()]


def list_dirs(path: str | None = None, *, limit: int = 500) -> DirListing:
    """Sub-directories of ``path`` (defaults to the user's home)."""
    start = pathlib.Path(path).expanduser() if path else pathlib.Path(home_dir())
    # Drive roots are always offered so the picker can jump between drives.
    return _list(start, limit=limit, roots=drive_roots())


def _list(start: pathlib.Path, *, limit: int, roots: list[str] | None = None) -> DirListing:
    listing = DirListing(path=str(start), roots=roots or [])
    try:
        resolved = start.resolve()
    except OSError as e:
        listing.exists = False
        listing.error = str(e)
        return listing
    if not resolved.is_dir():
        listing.path = str(resolved)
        listing.exists = False
        listing.error = "Not a folder"
        return listing
    listing.path = str(resolved)
    listing.protected = is_protected(resolved)
    parent = resolved.parent
    listing.parent = None if parent == resolved else str(parent)
    names: list[str] = []
    try:
        with os.scandir(resolved) as entries:
            for entry in entries:
                if len(names) >= limit:
                    break
                try:
                    if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                names.append(entry.name)
    except PermissionError:
        listing.error = "Permission denied"
    except OSError as e:
        listing.error = str(e)
    listing.dirs = sorted(names, key=str.lower)
    return listing
