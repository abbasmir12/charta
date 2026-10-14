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
from .core.config import AppConfig
from .core.extract import VisionFn
from .core.gaps import gaps_for_folder
from .core.llm import LLMClient
from .core.outputs import build_data_entry, build_receipts, build_study
from .core.paths import assert_not_protected
from .core.pipeline import process_new_file


def _client() -> LLMClient:
    return LLMClient(AppConfig.load())


def _vision(cfg: AppConfig, client: LLMClient) -> VisionFn | None:
    """Vision hook for scanned PDFs/images, or None when disabled."""
    return client.describe_image if cfg.vision else None


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
    vision = _vision(cfg, client)
    auto = ch.mode == "auto"

    def on_file(p: pathlib.Path) -> None:
        res = process_new_file(folder, p, ch, client, auto_apply=auto,
                               dry_run=args.dry_run, vision=vision)
        prop = res.proposal
        verb = "moved" if res.applied else ("would move" if auto else "proposed")
        dest = res.dst or f"{prop.dest_dir}/{prop.new_name}"
        print(f"{verb}: {prop.source} → {dest} ({prop.reason})")

    print(f"Watching {folder} (Ctrl+C to stop). Mode: {ch.mode}"
          f"{' [dry-run]' if args.dry_run else ''}.")
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
    up = LLMClient(cfg).ping()
    from .shell.native_window import is_windows

    print(f"Provider: {cfg.llm_provider} @ {cfg.llm_base_url} ({cfg.generation_model})")
    print(f"Window: {'native (Windows)' if is_windows() else 'browser fallback on this OS'}"
          f"{' [debug]' if cfg.debug else ''}")
    print(f"AI: {'up' if up else 'DOWN — check [llm] in config.toml'}"
          + ("" if up else " (offline: heuristic fallback still works)"))
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
    client = _client()
    cfg = AppConfig.load()
    idx = build_index(folder, client, vision=_vision(cfg, client))
    ans = answer_query(args.question, idx, client)
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
    import os

    import uvicorn

    cfg = AppConfig.load()
    if getattr(args, "debug", False):
        os.environ["CHARTA_DEBUG"] = "1"  # the app reads it per request
    uvicorn.run("charta.web.app:app", host=cfg.host, port=args.port or cfg.port, log_level="info")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Read-only environment report — the first thing to run on a new machine."""
    from .core.doctor import format_report, report_json, run_checks, verdict

    checks = run_checks(AppConfig.load(), ping=not args.no_ping)
    print(report_json(checks) if args.json else format_report(checks))
    return 0 if verdict(checks) else 1


def cmd_open(args: argparse.Namespace) -> int:
    """Native window (pywebview) or the default browser as a fallback."""
    import os

    from .shell.desktop import group_taskbar, run

    cfg = AppConfig.load()
    debug = bool(getattr(args, "debug", False)) or cfg.debug
    if debug:
        os.environ["CHARTA_DEBUG"] = "1"
    group_taskbar()  # group under one taskbar entry before the window opens
    return run(cfg.host, args.port or cfg.port, args.folder or "", debug=debug,
               state_dir=cfg.state_path(), mica=cfg.mica)


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
    p.add_argument("--dry-run", action="store_true",
                   help="in auto mode, log the move without performing it")
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
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=0)
    p.add_argument("--debug", action="store_true",
                   help="keep browser keys (F5, Ctrl+R/F/P, DevTools) for development")
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("open", help="open Charta in a native window (or your browser)")
    p.add_argument("folder", nargs="?", default="")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--debug", action="store_true")
    p.set_defaults(fn=cmd_open)
    p = sub.add_parser("doctor", help="check this machine's Charta setup (read-only)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-ping", action="store_true", help="skip the provider reachability check")
    p.set_defaults(fn=cmd_doctor)
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
