"""New-file pipeline shared by the watcher (CLI) and the UI.

extract -> sensitive check -> propose -> optionally apply (auto mode).
Keeping this in one place means suggest mode and auto mode move through
exactly the same safety path (protected paths, journal, collision suffix).
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from . import mover, proposals as prop_store
from .charter import Charter
from .classify import Proposal, propose_for_file
from .extract import VisionFn, extract_text
from .llm import LLMClient
from .sensitive import detect


@dataclass
class ProcessResult:
    proposal: Proposal
    applied: bool = False
    dst: str = ""


def process_new_file(folder: str | pathlib.Path, path: str | pathlib.Path,
                     charter: Charter, client: LLMClient | None = None,
                     auto_apply: bool = False, dry_run: bool = False,
                     vision: VisionFn | None = None) -> ProcessResult:
    """Handle one new file. Never moves anything unless ``auto_apply`` is set.

    ``dry_run`` keeps even auto mode side-effect free apart from the proposal
    record, so it stays safe to preview.
    """
    root = pathlib.Path(folder)
    p = pathlib.Path(path)
    extracted = extract_text(p, vision)
    report = detect(extracted.text)
    prop = propose_for_file(p.name, extracted.text, charter, client, report.sensitive)
    prop.source = str(p.relative_to(root)) if p.is_relative_to(root) else p.name
    prop_store.upsert(root, prop)

    if not (auto_apply and prop.status == "pending"):
        return ProcessResult(prop)
    if dry_run:
        return ProcessResult(prop, applied=False,
                             dst=str(pathlib.Path(prop.dest_dir) / prop.new_name))
    move = mover.apply_proposal(root, prop)
    prop.status = "approved"
    prop_store.upsert(root, prop)
    return ProcessResult(prop, applied=True, dst=move.dst)
