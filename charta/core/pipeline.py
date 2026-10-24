"""New-file pipeline shared by the watcher (CLI) and the UI.

extract -> sensitive check -> propose -> optionally apply (auto mode).
Keeping this in one place means suggest mode and auto mode move through
exactly the same safety path (protected paths, journal, collision suffix).
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from . import index_db, mover, proposals as prop_store
from .charter import Charter
from .classify import Proposal, propose_for_file
from .extract import VisionFn, extract_text
from .llm import LLMClient
from .meta import extract_metadata
from .sensitive import detect


@dataclass
class ProcessResult:
    proposal: Proposal
    applied: bool = False
    dst: str = ""


def organized_paths(root: pathlib.Path) -> set[str]:
    """ Every file a decided proposal already put in place (or rejected).

    Keyed by relative path with forward slashes: the proposal's own source
    plus its destination — so a file that an approval *renamed or moved* is
    not proposed again under its new name after a restart or a rescan.
    """
    paths: set[str] = set()
    for x in prop_store.load_proposals(root):
        if x.status not in ("approved", "rejected"):
            continue
        if x.source:
            paths.add(x.source.replace("\\", "/"))
        dest = x.dest_dir.replace("\\", "/").rstrip("/")
        target = "/".join(part for part in (dest, x.new_name) if part)
        if target:
            paths.add(target)
    return paths


def process_new_file(folder: str | pathlib.Path, path: str | pathlib.Path,
                     charter: Charter, client: LLMClient | None = None,
                     auto_apply: bool = False, dry_run: bool = False,
                     vision: VisionFn | None = None) -> ProcessResult:
    """Handle one new file. Never moves anything unless ``auto_apply`` is set.

    ``dry_run`` keeps even auto mode side-effect free apart from the proposal
    record, so it stays safe to preview.

    The file's text is read once, here: its metadata and chunks go into the
    folder's index, so Ask and Search work from that index instead of reading
    the folder again for every question.
    """
    root = pathlib.Path(folder)
    p = pathlib.Path(path)
    extracted = extract_text(p, vision)
    report = detect(extracted.text)
    prop = propose_for_file(p.name, extracted.text, charter, client, report.sensitive)
    prop.source = str(p.relative_to(root)) if p.is_relative_to(root) else p.name
    # A file an earlier approval already placed (possibly under a new name)
    # never returns to Review — the restart-scan must not undo the past.
    if prop.source not in organized_paths(root):
        prop_store.upsert(root, prop)
    _index_file(root, prop.source, extracted, report.sensitive)

    if not (auto_apply and prop.status == "pending"):
        return ProcessResult(prop)
    if dry_run:
        return ProcessResult(prop, applied=False,
                             dst=str(pathlib.Path(prop.dest_dir) / prop.new_name))
    move = mover.apply_proposal(root, prop)
    prop.status = "approved"
    prop_store.upsert(root, prop)
    # The file changed places: the index follows it.
    index_db.remove(root, prop.source)
    _index_file(root, move.dst, extracted, report.sensitive)
    return ProcessResult(prop, applied=True, dst=move.dst)


def _index_file(root: pathlib.Path, rel: str, extracted: object,
                sensitive: bool) -> None:
    """Store one file's metadata and text in the folder's index."""
    try:
        text = getattr(extracted, "text", "") or ""
        pages = int(getattr(extracted, "pages", 0) or 0)
        method = str(getattr(extracted, "method", "") or "")
        metadata = extract_metadata(rel, text, pages=pages, method=method)
        from .ask import chunk_text  # local import: keeps the module graph flat
        index_db.upsert(root, rel, text, metadata, pages=pages, method=method,
                        sensitive=sensitive, chunks=chunk_text(text))
    except Exception:  # noqa: BLE001 — the index is a convenience, never a blocker
        return
