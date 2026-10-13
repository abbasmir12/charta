"""Protected-path guard."""
from __future__ import annotations

import os
import pathlib


class ProtectedPathError(ValueError):
    pass


def is_protected(path: str | pathlib.Path) -> bool:
    """True if path must never be operated on."""
    p = str(path).replace("\\", "/").lower().rstrip("/")
    # Windows system locations (also match wine-style / drive prefixes)
    needles = ["c:/windows", "program files", "appdata", "c:/programdata"]
    if any(n in p for n in needles):
        return True
    # drive root e.g. C:/ or C:
    import re

    if re.fullmatch(r"[a-z]:/?", p):
        return True
    # bare "/" root
    if p in ("", "/"):
        return True
    # user profile root: ~ exactly
    try:
        home = str(pathlib.Path.home()).replace("\\", "/").lower().rstrip("/")
        if p == home:
            return True
    except Exception:
        pass
    # unix system dirs
    if p in ("/root", "/etc", "/bin", "/sbin", "/usr", "/var", "/sys", "/proc"):
        return True
    return False


def assert_not_protected(path: str | pathlib.Path) -> None:
    if is_protected(path):
        raise ProtectedPathError(
            f"Refusing to watch '{path}': system and profile-root folders are protected. "
            "Pick a subfolder (e.g. Documents/Receipts)."
        )
