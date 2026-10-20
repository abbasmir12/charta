"""One-command demo: build a messy folder, charter it, sort it, show the payoff.

Deterministic sample data and a preset charter mean the demo works with no
network and no model running (the heuristic fallback is enough); pass
``use_llm=True`` to let the configured model classify instead.
"""
from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass, field

from . import mover, proposals as prop_store
from .charter import Charter, preset_charter, save_charter
from .classify import Proposal
from .config import AppConfig
from .llm import LLMClient
from .outputs import build_data_entry, build_receipts, build_study
from .paths import assert_not_protected
from .pipeline import process_new_file

MARKER = ".charta/demo.json"

_SAMPLES: dict[str, dict[str, str]] = {
    "freelancer": {
        "receipt_edf_2026-03-14.txt": "receipt from EDF\ndate: 2026-03-14\ntotal: €87.40\ncategory: electricity",
        "receipt_free_2026-03-01.txt": "receipt from Free\ndate: 2026-03-01\ntotal: €29.99\ncategory: internet",
        "receipt_amazon_2026-04-11.txt": "receipt from Amazon\ndate: 2026-04-11\ntotal: $54.20\ncategory: office",
        "invoice_sncf_2026-02-02.txt": "invoice from SNCF\ndate: 2026-02-02\ntotal: €112.00\ncategory: travel",
        "invoice_rent_2026-04-01.txt": "invoice from Rent\ndate: 2026-04-01\ntotal: €780.00\ncategory: housing",
        "bank_statement_2026-03.txt": "bank statement\ndate: 2026-03-31\nbalance: €1,204.10",
        "tax_note.md": "Remember to mark the March electricity bill as a business expense.",
        "scan_001.txt": "handwritten note: plumber paid 45 euros, no receipt yet",
    },
    "student": {
        "lecture_01_algorithms.txt": "Lecture 1: algorithms\nKey point: Big-O describes growth.",
        "lecture_02_graphs.txt": "Lecture 2: graphs\nKey point: BFS finds shortest paths.",
        "lecture_03_dynamic.txt": "Lecture 3: dynamic programming\nKey point: memoize overlapping subproblems.",
        "lecture_04_trees.txt": "Lecture 4: trees\nKey point: a heap is a complete binary tree.",
        "assignment_01.txt": "Assignment 1: implement BFS and DFS. Due 2026-10-24.",
        "assignment_02.txt": "Assignment 2: prove the greedy choice. Due 2026-11-07.",
        "notes_graphs.md": "Graphs: adjacency list vs matrix; BFS vs DFS trade-offs.",
        "todos.txt": "Book exam slot; print lecture 5 slides.",
    },
    "data_entry": {
        "form_001.txt": "name: Amina Diallo\nphone: 0600000001\namount: 120",
        "form_002.txt": "name: Bruno Costa\nphone: 0600000002\namount: 75",
        "form_003.txt": "name: Chen Wei\nphone: 0600000003\namount: 240",
        "form_004.txt": "name: Diana Rossi\nphone: 0600000004\namount: 90",
        "form_005.txt": "name: Emeka Obi\nphone: 0600000005\namount: 180",
        "form_006.txt": "name: Fatima Zahra\nphone: 0600000006\namount: 60",
        "form_007.txt": "name: Gabriel Silva\nphone: 0600000007\namount: 300",
        "batch_note.txt": "Batch A: forms 001-007, typed and ready to export.",
    },
}


@dataclass
class DemoResult:
    folder: str
    preset: str
    before: list[str] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    outputs: dict = field(default_factory=dict)
    applied: bool = False
    used_llm: bool = False
    llm_files: int = 0
    purpose: str = ""


def tree(folder: str | pathlib.Path) -> list[str]:
    """Relative file paths, sorted, without the .charta bookkeeping folder."""
    root = pathlib.Path(folder)
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".charta" not in p.relative_to(root).parts:
            out.append(str(p.relative_to(root)))
    return out


def _write_samples(folder: pathlib.Path, preset: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARKER).parent.mkdir(parents=True, exist_ok=True)
    (folder / MARKER).write_text('{"made_by": "charta demo"}\n', encoding="utf-8")
    for name, text in _SAMPLES[preset].items():
        (folder / name).write_text(text + "\n", encoding="utf-8")


def prepare(folder: str | pathlib.Path, preset: str, reset: bool = False) -> pathlib.Path:
    """Create the demo folder, refusing to touch anything Charta did not make."""
    if preset not in _SAMPLES:
        raise ValueError(f"unknown preset: {preset}")
    root = pathlib.Path(folder)
    assert_not_protected(root)
    exists_ours = (root / MARKER).exists()
    if root.exists() and any(root.iterdir()):
        if not exists_ours:
            raise FileExistsError(
                f"refusing to touch a non-empty folder Charta did not create: {root}. "
                "Pick a new/empty path or run `charta demo --folder <new path>`.")
        if not reset:
            raise FileExistsError(
                f"demo folder already exists: {root}. Re-run with --reset to rebuild it.")
        shutil.rmtree(root)
    _write_samples(root, preset)
    return root


def run(folder: str | pathlib.Path, preset: str = "freelancer", *,
        apply: bool = True, use_llm: bool = False, reset: bool = False,
        client: LLMClient | None = None) -> DemoResult:
    """Build the folder, propose, optionally approve, then build outputs."""
    root = prepare(folder, preset, reset=reset)
    ch: Charter = preset_charter(preset)
    save_charter(root, ch)
    before = tree(root)
    if use_llm and client is None:
        client = LLMClient(AppConfig.load())

    proposals: list[Proposal] = []
    for rel in before:
        res = process_new_file(root, root / rel, ch, client if use_llm else None,
                               auto_apply=False)
        proposals.append(res.proposal)

    if apply:
        for prop in proposals:
            if prop.status != "pending":
                continue
            try:
                mover.apply_proposal(root, prop)
                prop.status = "approved"
            except Exception:  # noqa: BLE001 — one bad file must not abort the demo
                continue
        prop_store.save_proposals(root, proposals)

    outputs: dict = {}
    if apply:
        if preset == "freelancer":
            outputs = build_receipts(root)
        elif preset == "student":
            outputs = build_study(root)
        else:
            outputs = build_data_entry(root, ch.fields)

    llm_files = sum(1 for p in proposals if p.origin == "llm")
    return DemoResult(folder=str(root), preset=preset, before=before,
                      proposals=proposals, after=tree(root), outputs=outputs,
                      applied=apply, used_llm=llm_files > 0, llm_files=llm_files,
                      purpose=ch.purpose)
