"""Charta CLI — every mutating command has --dry-run. Same core as the UI."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .core import journal as journal_mod
from .core import mover as mover_mod
from .core import proposals as prop_store
from .core import record
from .core import watchlist as watchlist_mod
from .core.ask import answer_query, build_index
from .core.agent import ask_with_tools
from .core.charter import (create_charter_from_text, load_charter, preset_charter,
                           save_charter)
from .core import config as config_mod
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
    cfg = AppConfig.load()
    watched = watchlist_mod.folders(cfg)
    print(f"Folder: {folder}")
    print(f"Charter: {'yes — ' + (ch.purpose if ch else '')}" if ch else "Charter: none")
    print(f"Watching this folder: {'yes' if watchlist_mod.is_watched(cfg, folder) else 'no'}")
    print(f"Watched folders: {', '.join(watched) if watched else 'none'}")
    print(f"Proposals pending: {len([p for p in props if p.status == 'pending'])}")
    print(f"Journal entries: {len(journal_mod.entries(folder))}")
    up = LLMClient(cfg).ping()
    from .shell.native_window import is_windows

    print(f"Provider: {cfg.llm_provider} @ {cfg.llm_base_url} ({cfg.generation_model})")
    print(f"Window: {'native (Windows)' if is_windows() else 'browser fallback on this OS'}"
          f"{' [debug]' if cfg.debug else ''}")
    print(f"AI: {'up' if up else 'DOWN — check [llm] in config.toml'}"
          + ("" if up else " (offline: heuristic fallback still works)"))
    return 0


def cmd_watchd(args: argparse.Namespace) -> int:
    """Run the background watcher in the foreground (Ctrl+C to stop)."""
    import time

    from .core.watchd import WatchDaemon

    cfg = AppConfig.load()
    daemon = WatchDaemon(cfg)
    daemon.start()
    active = daemon.tick()
    print(f"Watch daemon: {', '.join(active) if active else 'nothing watched yet'}"
          " (Ctrl+C to stop).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        daemon.stop()
    return 0


def cmd_unwatch(args: argparse.Namespace) -> int:
    cfg = AppConfig.load()
    watchlist_mod.remove(cfg, args.folder)
    rest = watchlist_mod.folders(cfg)
    print(f"Stopped watching {args.folder}."
          + (f" Still watching: {', '.join(rest)}" if rest else ""))
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
    moves: list[tuple[str, str, str]] = []
    for p in targets:
        try:
            r = mover_mod.apply_proposal(folder, p, dry_run=args.dry_run)
            print(f"{'[dry-run] would move' if args.dry_run else 'moved'}: {r.src} → {r.dst} ({r.reason})")
            if not args.dry_run:
                p.status = "approved"
                moves.append((r.src, r.dst, r.reason))
        except Exception as e:  # noqa: BLE001
            print(f"FAILED {p.source}: {e}")
    if not args.dry_run:
        prop_store.save_proposals(folder, props)
        record.record_moves(AppConfig.load(), folder, moves)
        # refresh outputs
        build_receipts(folder)
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    e = journal_mod.undo_last(args.folder, dry_run=args.dry_run)
    print(f"{'[dry-run] would undo' if args.dry_run else 'undone'}: {e}" if e else "Journal empty.")
    if e and not args.dry_run:
        record.record_undo(AppConfig.load(), args.folder, e.get("src", ""), e.get("dst", ""))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    folder = pathlib.Path(args.folder)
    ch = load_charter(folder)
    client = _client()
    cfg = AppConfig.load()
    stats: dict = {}
    idx = build_index(folder, vision=_vision(cfg, client), stats=stats)
    if not idx:
        print(f"Nothing indexed in {folder} yet — run: charta watch --folder {folder} --scan")
        return 1
    # The agent: the model gets the index and the tools, and calls them itself.
    steps: list[dict] = []
    agent = ask_with_tools(args.question, folder, client, steps=steps)
    for s in steps:
        print(f"  · {s['text']}")
    if agent.used_tools and agent.answer:
        print(agent.answer)
        for c in agent.citations:
            print(f"  [{c.file} p{c.page}] {c.excerpt[:120]}")
        print(f"  (tools: {', '.join(c.name for c in agent.calls)}; "
              f"model {cfg.llm_provider}/{cfg.generation_model})")
        return 0
    ans = answer_query(args.question, idx, client)
    print(ans.text)
    for c in ans.citations:
        print(f"  [{c.file} p{c.page}] {c.excerpt[:120]}")
    print(f"  (read {stats.get('indexed', len(idx))} of {stats.get('files', len(idx))} file(s)"
          f" in {stats.get('seconds', 0)}s"
          + (" — some files were left out to keep it quick" if stats.get("truncated") else "")
          + f"; model {cfg.llm_provider}/{cfg.generation_model})")
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


def _print_paths(paths: list[str], indent: str = "  ") -> None:
    for rel in paths:
        print(f"{indent}{rel}")


def cmd_demo(args: argparse.Namespace) -> int:
    """Build a messy sample folder and show the sort + output payoff."""
    from .core.demo import run

    folder = pathlib.Path(args.folder)
    try:
        res = run(folder, args.preset, apply=not args.dry_run, use_llm=args.ai,
                  reset=args.reset)
    except Exception as e:  # noqa: BLE001
        print(f"Cannot set up demo: {e}")
        return 2
    if res.used_llm:
        mode = f"configured model ({res.llm_files}/{len(res.proposals)} files)"
    elif args.ai:
        mode = "offline heuristic — the configured model did not answer (run: charta doctor)"
    else:
        mode = "offline heuristic (no model needed)"
    print(f"Charta demo — {res.preset} — {mode}\n")
    print(f"Folder: {res.folder}")
    print(f"Before: {len(res.before)} files, flat")
    _print_paths(res.before)
    print(f"\nCharter: .charta/charter.md — {res.purpose}")
    print(f"\n{'Would move' if args.dry_run else 'Proposed'} ({len(res.proposals)}):")
    for p in res.proposals:
        flag = " [SENSITIVE]" if p.sensitive else ""
        print(f"  {p.source} → {p.dest_dir}/{p.new_name}{flag}")
        print(f"     {p.reason} (conf {p.confidence:.2f})")
    if args.dry_run:
        print("\n[dry-run] nothing moved, nothing written.")
        return 0
    print(f"\nAfter: {len(res.after)} files organized")
    _print_paths(res.after)
    if res.outputs:
        print("\nOutput you did not have to make by hand:")
        seen: set[str] = set()
        for k, v in res.outputs.items():
            if not isinstance(v, str) or v in seen:
                continue
            seen.add(v)
            rel = pathlib.Path(v).relative_to(folder) if pathlib.Path(v).is_relative_to(folder) else v
            print(f"  {rel}")
        if "rows" in res.outputs:
            print(f"  ({res.outputs['rows']} rows)")
        if res.outputs.get("xlsx") == res.outputs.get("csv"):
            print("  (Excel copy skipped — install openpyxl to also get receipts.xlsx)")
    print("\nNothing was deleted. Every move is journaled.")
    print(f"Undo one step:  charta undo --folder \"{res.folder}\"")
    print(f"See it in the UI: charta open --folder \"{res.folder}\"")
    if args.watch:
        cfg = AppConfig.load()
        ch = load_charter(folder)
        watchlist_mod.add(cfg, folder, ch.mode if ch else "")
        print("Now watching this folder in the background.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    from .core import applog
    from .shell.desktop import choose_port

    cfg = AppConfig.load()
    log = applog.setup(cfg)
    if getattr(args, "debug", False):
        os.environ["CHARTA_DEBUG"] = "1"  # the app reads it per request
    port = args.port or cfg.port
    if port and not getattr(args, "strict_port", False):
        port, note = choose_port(cfg.host, port)
        if note:
            print(f"charta: {note}")
            applog.get_logger("serve").info(note)
    print(f"serving on http://{cfg.host}:{port}   log: {log}")
    applog.write_session(cfg, pid=os.getpid(), port=port, host=cfg.host, view="serve")
    try:
        uvicorn.run("charta.web.app:app", host=cfg.host, port=port, log_level="info")
    finally:
        applog.clear_session(cfg, "server stopped")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Read-only environment report — the first thing to run on a new machine."""
    from .core.doctor import format_report, report_json, run_checks, verdict

    checks = run_checks(AppConfig.load(), ping=not args.no_ping)
    print(report_json(checks) if args.json else format_report(checks))
    return 0 if verdict(checks) else 1


def cmd_testmodel(args: argparse.Namespace) -> int:
    """Send a short prompt to the configured model and show the reply + status."""
    import json

    from .core.doctor import test_model

    cfg = AppConfig.load()
    report = test_model(cfg, prompt=args.prompt, timeout=args.timeout)
    config_files = config_mod.config_files()

    if args.json:
        print(json.dumps({"ok": report.ok, "provider": report.provider,
                          "base_url": report.base_url, "model": report.model,
                          "config": [str(f) for f in config_files],
                          "prompt": report.prompt, "reachable": report.reachable,
                          "model_listed": report.model_listed, "reply": report.reply,
                          "error": report.error, "seconds": round(report.seconds, 3)},
                         indent=2))
        return 0 if report.ok else 1

    lines = ["Charta model test", "=" * 17,
             f"provider  {report.provider}",
             f"endpoint  {report.base_url}",
             f"model     {report.model}",
             f"config    {config_mod.config_path()}",
             "",
             f"prompt    {report.prompt}",
             ""]
    if report.reachable:
        lines.append("[OK  ] reachable   provider answered on /models")
    else:
        lines.append("[FAIL] reachable   no answer on /models")
        lines.append("       └─ start it (Ollama: `ollama serve`) or set CHARTA_BASE_URL")
    if report.model_listed is None:
        lines.append("[OK  ] model       provider cannot list models (not checked)")
    elif report.model_listed:
        lines.append(f"[OK  ] model       {report.model} is offered by the provider")
    else:
        lines.append(f"[FAIL] model       {report.model} is not offered by the provider")
        lines.append(f"       └─ set [models] generation or run: ollama pull {report.model}")
    if report.reply:
        lines.append(f'[OK  ] answer      "{report.reply}" ({report.seconds:.1f}s)')
    else:
        lines.append(f"[FAIL] answer      {report.seconds:.1f}s")
        lines.append(f"       └─ {report.error}")

    if report.ok:
        lines += ["", "Status: PASS — the model is answering through Charta."]
    else:
        hint = (f"\nTry `charta doctor` for the full picture, or `charta testmodel "
                f'--prompt "hi" --timeout 30` for a slower model.')
        lines += ["", "Status: FAIL — the model did not answer." + hint]
    print("\n".join(lines))
    return 0 if report.ok else 1


def cmd_open(args: argparse.Namespace) -> int:
    """Native window (Electron or pywebview), or the default browser as a fallback."""
    import os

    from .shell.desktop import group_taskbar, run

    cfg = AppConfig.load()
    debug = bool(getattr(args, "debug", False)) or cfg.debug
    if debug:
        os.environ["CHARTA_DEBUG"] = "1"
    group_taskbar()  # group under one taskbar entry before the window opens
    return run(cfg, args.folder or "", debug=debug, port=args.port or cfg.port,
               browser_only=bool(getattr(args, "browser", False)))


def cmd_logs(args: argparse.Namespace) -> int:
    """Print the tail of the log file (the only evidence left after a silent exit)."""
    from .core.applog import log_path, read_log, read_session, session_running

    cfg = AppConfig.load()
    print(f"{log_path(cfg)}\n")
    if session_running(cfg):
        print(f"Charta is still running: {read_session(cfg)}\n")
    print(read_log(cfg, lines=args.lines))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Close the running Charta backend, cleanly and only that one.

    The pid comes from the session file. If the recorded port is still open,
    that instance is stopped; if it is closed, the session was stale and is
    only cleared — nothing else on the machine is ever touched.
    """
    import os
    import signal

    from .core.applog import read_session, session_running, clear_session

    cfg = AppConfig.load()
    if not session_running(cfg):
        # The port is not answering: the instance is gone. Clear the stale
        # session and never gamble on what the old pid belongs to now.
        clear_session(cfg, "stale session")
        print("Charta is not running (cleared the stale session if there was one).")
        return 0
    session = read_session(cfg)
    pid = int(session.get("pid") or 0)
    if pid <= 0 or pid == os.getpid():
        clear_session(cfg, "stale session")
        print("The session was stale — cleared it.")
        return 0
    try:
        if os.name == "nt":
            os.system(f"taskkill /PID {pid} /F")
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"Could not stop pid {pid}: {e}")
        return 1
    clear_session(cfg, "stopped")
    print(f"Stopped Charta (pid {pid}). Start it again with: charta open .")
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
    p = sub.add_parser("demo", help="build a messy sample folder and show the payoff")
    p.add_argument("--folder", default="charta-demo")
    p.add_argument("--preset", default="freelancer",
                   choices=["freelancer", "student", "data_entry"])
    p.add_argument("--reset", action="store_true", help="rebuild an existing demo folder")
    p.add_argument("--dry-run", action="store_true", help="propose only; move/write nothing")
    p.add_argument("--ai", action="store_true", help="let the configured model classify")
    p.add_argument("--watch", action="store_true", help="add the demo folder to the watchlist")
    p.set_defaults(fn=cmd_demo)
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=0)
    p.add_argument("--debug", action="store_true",
                   help="keep browser keys (F5, Ctrl+R/F/P, DevTools) for development")
    p.add_argument("--strict-port", action="store_true",
                   help="fail instead of picking another port when this one is busy")
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("open", help="open Charta in a native window (or your browser)")
    p.add_argument("folder", nargs="?", default="")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--browser", action="store_true", help="skip the native window, use a browser")
    p.set_defaults(fn=cmd_open)
    p = sub.add_parser("logs", help="show the Charta log (startup, errors, exit reason)")
    p.add_argument("--lines", type=int, default=60); p.set_defaults(fn=cmd_logs)
    p = sub.add_parser("stop", help="close the running Charta cleanly (safe: only the recorded pid)")
    p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("doctor", help="check this machine's Charta setup (read-only)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-ping", action="store_true", help="skip the provider reachability check")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("testmodel", help="ask the configured model 'hello' and show the reply")
    p.add_argument("--prompt", default="hello", help="prompt to send (default: hello)")
    p.add_argument("--timeout", type=float, default=30.0, help="seconds to wait for the answer")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_testmodel)
    p = sub.add_parser("install-shell"); p.set_defaults(fn=lambda a: cmd_shell(a, True))
    p = sub.add_parser("uninstall-shell"); p.set_defaults(fn=lambda a: cmd_shell(a, False))
    p = sub.add_parser("watchd", help="run the background watcher for every watched folder")
    p.set_defaults(fn=cmd_watchd)
    p = sub.add_parser("unwatch"); p.add_argument("--folder", default=".")
    p.set_defaults(fn=cmd_unwatch)
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
