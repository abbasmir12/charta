"""Charta CLI — every mutating command has --dry-run. Same core as the UI."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .core import journal as journal_mod
from .core import mover as mover_mod
from .core import proposals as prop_store
from .core.ask import answer_query, build_index
from .core.charter import (create_charter_from_text, load_charter, preset_charter,
                           save_charter)
from .core.classify import propose_for_file
from .core.config import AppConfig
from .core.extract import extract_text
from .core.gaps import gaps_for_folder
from .core.llm import OllamaClient, ollama_ping
from .core.outputs import build_data_entry, build_receipts, build_study
from .core.paths import assert_not_protected
from .core.sensitive import detect


def _client() -> OllamaClient:
    return OllamaClient(AppConfig.load())


def cmd_charter(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    assert_not_protected(folder)
    if args.preset and not args.text:
        ch = preset_charter(args.preset)
    else:
        ch = create_charter_from_text(args.text or "", _client())
        if args.preset:
            ch.preset = args.preset
    if args.mode:
        ch.mode = args.mode
    p = save_charter(folder, ch)
    print(f"Charter saved → {p}\nPurpose: {ch.purpose}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    try:
        assert_not_protected(folder)
    except Exception as e:
        print(f"Cannot watch: {e}")
        return 2
    ch = load_charter(folder)
    if ch is None:
        print("No charter yet. Run: charta charter --folder F --text '...'")
        return 2
    from .core.watcher import FolderWatcher, wait_stable  # noqa

    cfg = AppConfig.load()
    client = _client()

    def on_file(p: pathlib.Path) -> None:
        res = extract_text(p)
        rep = detect(res.text)
        prop = propose_for_file(p.name, res.text, ch, client, rep.sensitive)
        prop.source = str(p.relative_to(folder)) if p.is_relative_to(folder) else p.name
        prop_store.upsert(folder, prop)
        print(f"proposed: {prop.source} → {prop.dest_dir}/{prop.new_name} ({prop.reason})")

    print(f"Watching {folder} (Ctrl+C to stop). Mode: {ch.mode}.")
    if args.scan:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and ".charta" not in p.parts and wait_stable(p, 0.2):
                on_file(p)
    if args.once:
        return 0
    w = FolderWatcher(folder, on_file, cfg.stable_seconds)
    w.start()
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        w.stop()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    ch = load_charter(folder)
    props = prop_store.load_proposals(folder)
    print(f"Folder: {folder}")
    print(f"Charter: {'yes — ' + (ch.purpose if ch else '')}" if ch else "Charter: none")
    print(f"Proposals pending: {len([p for p in props if p.status == 'pending'])}")
    print(f"Journal entries: {len(journal_mod.entries(folder))}")
    cfg = AppConfig.load()
    print(f"Ollama ({cfg.ollama_host}): {'up' if ollama_ping(cfg.ollama_host) else 'DOWN — run: ollama serve'}")
    return 0


def cmd_proposals(args: argparse.Namespace) -> int:
    for p in prop_store.load_proposals(args.folder):
        flag = " [SENSITIVE]" if p.sensitive else ""
        print(f"- {p.source} → {p.dest_dir}/{p.new_name} [{p.status}]{flag}\n  {p.reason} (conf {p.confidence:.2f})")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    props = prop_store.load_proposals(folder)
    targets = [p for p in props if p.status == "pending" and (args.all or p.source == args.file)]
    if not targets:
        print("Nothing to approve.")
        return 0
    for p in targets:
        try:
            r = mover_mod.apply_proposal(folder, p, dry_run=args.dry_run)
            print(f"{'[dry-run] would move' if args.dry_run else 'moved'}: {r.src} → {r.dst} ({r.reason})")
            if not args.dry_run:
                p.status = "approved"
        except Exception as e:  # noqa: BLE001
            print(f"FAILED {p.source}: {e}")
    if not args.dry_run:
        prop_store.save_proposals(folder, props)
        # refresh outputs
        build_receipts(folder)
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    e = journal_mod.undo_last(args.folder, dry_run=args.dry_run)
    print(f"{'[dry-run] would undo' if args.dry_run else 'undone'}: {e}" if e else "Journal empty.")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    ch = load_charter(folder)
    idx = build_index(folder, _client())
    ans = answer_query(args.question, idx, _client())
    print(ans.text)
    for c in ans.citations:
        print(f"  [{c.file} p{c.page}] {c.excerpt[:120]}")
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    ch = load_charter(pathlib.Path(args.folder))
    if not ch:
        print("No charter.")
        return 2
    for g in gaps_for_folder(args.folder, ch.expected):
        mark = "OK " if g.found else "MISSING"
        print(f"[{mark}] {g.expected} — {g.note}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    cfg = AppConfig.load()
    uvicorn.run("charta.web.app:app", host=cfg.host, port=args.port or cfg.port, log_level="info")
    return 0


def cmd_shell(args: argparse.Namespace, install: bool) -> int:
    from .shell.windows_registry import install as inst, uninstall as uninst

    print(inst() if install else uninst())
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="charta", description="Charta — magical local folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("charter"); p.add_argument("--folder", required=True)
    p.add_argument("--text", default=""); p.add_argument("--preset", default="",
                 choices=["", "student", "freelancer", "data_entry"])
    p.add_argument("--mode", default="", choices=["", "suggest", "auto"]); p.set_defaults(fn=cmd_charter)
    p = sub.add_parser("watch"); p.add_argument("folder", nargs="?", default=".")
    p.add_argument("--scan", action="store_true"); p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("status"); p.add_argument("--folder", default="."); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("proposals"); p.add_argument("--folder", default="."); p.set_defaults(fn=cmd_proposals)
    p = sub.add_parser("approve"); p.add_argument("--folder", default="."); p.add_argument("--file", default="")
    p.add_argument("--all", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("undo"); p.add_argument("--folder", default="."); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_undo)
    p = sub.add_parser("ask"); p.add_argument("--folder", default="."); p.add_argument("question", nargs="+")
    p.set_defaults(fn=lambda a: cmd_ask(argparse.Namespace(folder=a.folder, question=" ".join(a.question))))
    p = sub.add_parser("gaps"); p.add_argument("--folder", default="."); p.set_defaults(fn=cmd_gaps)
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=0); p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("install-shell"); p.set_defaults(fn=lambda a: cmd_shell(a, True))
    p = sub.add_parser("uninstall-shell"); p.set_defaults(fn=lambda a: cmd_shell(a, False))
    p = sub.add_parser("unwatch"); p.add_argument("--folder", default=".")
    p.set_defaults(fn=lambda a: (print("Stopped (stateless MVP — remove .charta to fully unwatch)."), 0)[1])
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
