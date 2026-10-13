"""Mover: dry-run, collision suffix, protected-path refusal, journal."""
from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass

from . import journal
from .classify import Proposal
from .paths import ProtectedPathError, assert_not_protected


@dataclass
class MoveResult:
    moved: bool
    src: str
    dst: str
    reason: str
    dry_run: bool = False


def unique_dest(dest: pathlib.Path) -> pathlib.Path:
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    i = 2
    while True:
        cand = dest.parent / f"{stem} ({i}){suf}"
        if not cand.exists():
            return cand
        i += 1


def apply_proposal(folder: str | pathlib.Path, prop: Proposal, dry_run: bool = False) -> MoveResult:
    root = pathlib.Path(folder)
    assert_not_protected(root)
    src = root / prop.source
    # dest_dir is relative; guard traversal
    dest_dir = pathlib.Path(prop.dest_dir)
    if dest_dir.is_absolute() or ".." in dest_dir.parts:
        raise ProtectedPathError(f"Refusing unsafe destination: {prop.dest_dir}")
    dst = unique_dest(root / dest_dir / prop.new_name)
    if dry_run:
        return MoveResult(False, str(src), str(dst), prop.reason, True)
    if not src.exists():
        raise FileNotFoundError(f"Source missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    rel_src = str(src.relative_to(root)) if src.is_relative_to(root) else str(src)
    rel_dst = str(dst.relative_to(root)) if dst.is_relative_to(root) else str(dst)
    journal.record(root, rel_src, rel_dst, prop.reason)
    return MoveResult(True, rel_src, rel_dst, prop.reason, False)
