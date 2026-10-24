"""Proposal store (.charta/proposals.json)."""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict

from .classify import Proposal


def _path(folder: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(folder) / ".charta" / "proposals.json"


def load_proposals(folder: str | pathlib.Path) -> list[Proposal]:
    p = _path(pathlib.Path(folder))
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Proposal(**d) for d in data]


def save_proposals(folder: str | pathlib.Path, props: list[Proposal]) -> None:
    p = _path(pathlib.Path(folder))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(x) for x in props], indent=2), encoding="utf-8")


def upsert(folder: str | pathlib.Path, prop: Proposal) -> None:
    props = load_proposals(folder)
    for i, x in enumerate(props):
        if x.source == prop.source:
            # A decided proposal stays decided. Re-proposing the same file
            # after a restart put it back into Review again and again.
            if x.status in ("approved", "rejected"):
                return
            props[i] = prop
            break
    else:
        props.append(prop)
    save_proposals(folder, props)
