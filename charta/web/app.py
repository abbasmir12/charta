"""FastAPI local UI: setup, overview, review, outputs, gaps, ask, activity, settings, styleguide."""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import re
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import icons
from ..core import applog
from ..core import chats
from ..core import fsbrowse
from ..core import history
from ..core import index_db
from ..core import journal as journal_mod
from ..core import mover as mover_mod
from ..core import proposals as prop_store
from ..core import record
from ..core import tools
from ..core import watchlist
from ..core.ask import answer_query, build_index, index_signature
from ..core.agent import TOOL_SPECS, ask_with_tools, structured_answer

TOOL_HINT = ("search_index looks through the folder's metadata (names, descriptions, "
             "tags, dates, amounts); read_file reads one file; list_files shows what "
             "is there. Every call is shown above as it happens.")
from ..core.charter import create_charter_from_text, load_charter, save_charter
from ..core.config import AppConfig
from ..core.config import load_document, save_document
from ..core.config import PROVIDER_BASE_URLS, config_path
from ..core.extract import VisionFn, extract_text
from ..core.llm import LLMClient
from ..core.outputs import build_data_entry, build_receipts, build_study
from ..core.paths import ProtectedPathError, assert_not_protected
from ..core.watchd import WatchDaemon, scan_folder

STATIC = pathlib.Path(__file__).parent / "static"
ASSETS = pathlib.Path(__file__).parent.parent / "assets"
ICON = ASSETS / "charta.ico"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> Any:
    """Resume watching every remembered folder (survives closing to the tray)."""
    try:
        _resume_watching()
    except Exception:  # noqa: BLE001 - a bad watchlist must not stop the UI
        pass
    try:
        yield
    finally:
        _stop_daemon()


app = FastAPI(title="Charta", lifespan=_lifespan)
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def _never_cache_ourselves(request: Request, call_next):
    """Pages and scripts must never come from the browser's cache.

    Electron keeps pages open for days; the app is updated while they are
    open. A cached `app.js` running against a changed API looks like a
    broken feature (it *was* "No answer." for days). Revalidation is free on
    a localhost server, so: never cache.
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response

THINKING: dict[str, str] = {"msg": "Idle. Watching nothing yet."}

_daemon: WatchDaemon | None = None
_daemon_lock = threading.Lock()
# Background scan jobs: id -> progress. Kept small (the last few jobs).
_scan_jobs: dict[str, dict] = {}
_scan_lock = threading.Lock()


def _daemon_get() -> WatchDaemon:
    global _daemon
    with _daemon_lock:
        if _daemon is None:
            _daemon = WatchDaemon(_cfg())
        return _daemon


def _stop_daemon() -> None:
    global _daemon
    with _daemon_lock:
        daemon, _daemon = _daemon, None
    if daemon:
        daemon.stop()


def _refresh_thinking() -> None:
    watched = watchlist.folders(_cfg())
    THINKING["msg"] = (f"Watching {len(watched)} folder{'s' if len(watched) != 1 else ''}."
                       if watched else "Idle. Watching nothing yet.")


def _sync_explorer_markers() -> None:
    """Best-effort: keep the per-folder Explorer verbs in step (Windows only)."""
    try:
        from ..shell import windows_registry

        windows_registry.sync_watched(watchlist.folders(_cfg()))
    except Exception:  # noqa: BLE001 - shell integration is optional
        pass


def _resume_watching() -> None:
    if watchlist.folders(_cfg()):
        _daemon_get().start()
    _refresh_thinking()
    _sync_explorer_markers()



def _cfg() -> AppConfig:
    return AppConfig.load()


def _client() -> LLMClient:
    return LLMClient(_cfg())


def _vision(cfg: AppConfig, client: LLMClient) -> VisionFn | None:
    return client.describe_image if cfg.vision else None


def _debug() -> bool:
    """Debug mode (CLI --debug / CHARTA_DEBUG): re-enables the browser's own keys."""
    return _cfg().debug


def dropdown(name: str, options: list[tuple[str, str]], selected: str) -> str:
    """Custom in-app dropdown (native <select> can't be themed or animated)."""
    chosen = next((label for value, label in options if value == selected), options[0][1])
    items = "".join(
        f'<li role="option" data-value="{value}" aria-selected="{"true" if value == selected else "false"}"'
        f' class="{"sel" if value == selected else ""}">{label}</li>'
        for value, label in options)
    return (f'<div class="dd" data-name="{name}" data-value="{selected}">'
            f'<button type="button" class="dd-btn" aria-haspopup="listbox" aria-expanded="false">{chosen}</button>'
            f'<ul class="dd-menu" role="listbox" hidden>{items}</ul>'
            f'<input type="hidden" name="{name}" value="{selected}"></div>')


def folder_picker_html() -> str:
    """Custom folder picker modal (dirs only; protected folders flagged, not selectable)."""
    return """<div id="fsPicker" class="picker-backdrop" hidden role="dialog" aria-modal="true" aria-label="Choose a folder">
<div class="card picker"><div class="picker-head">
<button type="button" class="btn btn-ghost" id="fsUp" aria-label="Parent folder">↑ Up</button>
<span class="mono" id="fsPath" aria-live="polite">…</span></div>
<ul id="fsList" class="picker-list" role="listbox" aria-label="Folders"></ul>
<p id="fsNote" class="picker-note" role="status"></p>
<div class="picker-foot"><span class="chip">No files shown — folders only</span>
<button type="button" class="btn" onclick="closePicker()">Cancel</button>
<button type="button" class="btn btn-primary" id="fsUse" onclick="usePickedFolder()">Use this folder</button>
</div></div></div>"""


NAV_ITEMS = ["folders", "overview", "files", "review", "outputs", "gaps", "ask",
             "search", "activity", "history", "settings"]
NAV_LABELS = {"folders": "Folders", "overview": "Overview", "files": "Files",
              "review": "Review", "outputs": "Outputs",
              "gaps": "Gaps", "ask": "Ask", "search": "Search",
              "activity": "Activity", "history": "History", "settings": "Settings"}
# Grouped navigation: high-frequency work first, records second, settings in the foot.
NAV_GROUPS = [("Work", ["folders", "overview", "files", "review", "outputs", "gaps", "ask"]),
              ("Records", ["search", "activity", "history"])]
LOCAL_PROVIDERS = ("ollama", "lmstudio", "llamacpp", "vllm")
# When this backend started — the Settings page shows it, so a window that is
# running older code (a leftover instance) is obvious at a glance.
_STARTED = datetime.datetime.now().isoformat(timespec="seconds")


def _code_revision() -> str:
    """The git revision this server is running from (best effort)."""
    import subprocess

    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10,
                             cwd=str(pathlib.Path(__file__).resolve().parent.parent))
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# A stamp the page can compare with the server: if they differ, the server was
# updated while this window was open, and the page asks to be reloaded.
BUILD = _STARTED


def icon(name: str, size: int = 18) -> str:
    """Inline icon by semantic name (see charta/web/icons.py)."""
    return icons.svg(name, size)


def _basename(folder: str) -> str:
    """Last path segment, tolerating Windows separators."""
    if not folder:
        return ""
    return pathlib.PurePath(folder.replace("\\", "/")).name or folder


def _remembered_folder(cfg: AppConfig) -> str:
    """The folder the user last worked with, best effort.

    The rail must show the same full set of pages on first launch as it does
    after a day's work: when the URL carries no folder, the remembered one is
    the honest default (the pages themselves still explain what a pick means).
    """
    try:
        entries = watchlist.known(cfg)
    except Exception:  # noqa: BLE001 - a broken registry must not break the shell
        return ""

    def stamp(e: dict) -> str:
        return max(e.get("last_scan") or "", e.get("added_at") or "")

    live = [e for e in entries if e.get("watching", True)] or entries
    if not live:
        return ""
    newest = sorted(live, key=stamp, reverse=True)
    return str(newest[0].get("folder", "") or "")


def _nav(items: list[str], page: str, fq: str) -> str:
    """The rail. Always complete: folder pages without a chosen folder land on
    their own "pick a folder" state, so the sidebar never half-disappears on a
    first run (it used to show only Folders + Search until a query param
    happened to carry a folder — the reason navigation looked to grow)."""
    out = []
    for n in items:
        out.append(
            f'<a href="/{n}?folder={fq}" class="{"active" if page == n else ""}"'
            f'{" aria-current=\"page\"" if page == n else ""}>'
            f'<span class="icon">{icon(n)}</span> {NAV_LABELS[n]}</a>')
    return "".join(out)


def shell(page: str, folder: str, inner: str, mode: str = "suggest", label: str = "") -> str:
    """App shell: toolbar + grouped navigation rail + content (every screen).

    The same markup is an ordinary header in a browser and the draggable window
    title bar inside Electron (desktop/preload.js sets data-shell).
    """
    # The rail (and everything it links) works from the folder in the URL; on
    # the very first screens (no ?folder= yet) it starts where the user last
    # left off, so navigation looks the same from minute one — never a
    # half-empty sidebar that "grows" after a first click.
    folder = folder or _remembered_folder(_cfg())
    fq = quote(folder)  # folder paths contain spaces, & and backslashes
    name = _basename(folder)
    here = label or NAV_LABELS.get(page) or (page.title() if page else "New charter")
    provider = _cfg().llm_provider
    if provider in LOCAL_PROVIDERS:
        status = ('<button type="button" class="status" onclick="openSettings()" '
                  'title="Where the AI runs is set by [llm] in config.toml.">'
                  f'<span class="icon">{icon("shield", 14)}</span> 100% local</button>')
    else:
        status = ('<button type="button" class="status" onclick="openSettings()" '
                  f'title="This folder sends text to {provider}.">'
                  f'<span class="icon">{icon("info", 14)}</span> Cloud: {provider}</button>')
    work = _nav(NAV_GROUPS[0][1], page, fq)
    records = _nav(NAV_GROUPS[1][1], page, fq)
    # under Ask: the folder's saved conversations, collapsible in the rail
    conv_block = ""
    if fq:
        saved = chats.list_chats(folder, 14)
        conv_items = "".join(
            f'<a class="conv-item" href="/ask?folder={fq}&chat={escape_attr(c["id"])}" '
            f'data-chat="{escape_attr(c["id"])}" onclick="openChat(this.dataset.chat);return false;" '
            f'title="open this conversation">'
            f'<span class="cv-t">{escape_attr(c["title"])}</span>'
            f'<span class="cv-m">{escape_attr(chats.meta_line(c["count"], c.get("updated") or ""))}</span></a>'
            for c in saved)
        empty = '<p class="cv-empty muted">No conversations yet — ask something below.</p>'
        conv_block = (
            f'<details class="conv-tree" id="convtree"{" open" if saved else ""}>'
            f'<summary title="This folder\'s saved Ask conversations">'
            f'<span class="icon">{icon("chevron-right", 14)}</span>'
            f'<span class="rail-sub-label">Conversations</span>'
            f'<span class="spacer"></span>'
            f'<button type="button" class="plusbtn" onclick="newChat(event)" '
            f'title="New conversation" aria-label="New conversation">'
            f'<span class="icon">{icon("plus", 15)}</span></button></summary>'
            f'<div class="conv-list" id="convlist" role="list">{conv_items or empty}</div></details>')
    settings_active = "active" if page == "settings" else ""
    folder_crumb = (
        f'<button type="button" class="crumb" onclick="openPicker()" title="{folder}">'
        f'<span class="icon">{icon("folder", 15)}</span><span class="name">{name}</span>'
        f'<span class="icon">{icon("chevron-down", 14)}</span></button>'
        f'<span class="crumb-sep" aria-hidden="true">/</span>') if name else ""
    return f"""<!doctype html><html data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><title>Charta — {page.title() if page else 'Setup'}</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/app.css">
<script>window.__CHARTA_DEBUG__={"true" if _debug() else "false"};window.__CHARTA_BUILD__={BUILD!r};window.__ICONS__={icons.manifest()};</script></head>
<body>
<header class="appbar" id="appbar">
<span class="brand"><span class="mark" aria-hidden="true">{icon("file", 13)}</span> Charta</span>
<nav class="crumbs" aria-label="Breadcrumb">{folder_crumb}<span class="crumb-cur">{here}</span></nav>
<span id="thinking" class="live" role="status" aria-live="polite">{THINKING['msg']}</span>
<span class="spacer"></span>
<button type="button" class="search" onclick="openPalette()" aria-label="Search and commands">
<span class="icon">{icon("search", 15)}</span><span>Search</span><span class="kbd">Ctrl K</span></button>
<a class="search" href="/search?folder={fq}" aria-label="Search the file index">
<span class="icon">{icon("search", 15)}</span><span>Files</span></a>
{status}
<button type="button" class="btn btn-icon btn-ghost" onclick="toggleTheme()" aria-label="Switch theme">
<span class="icon" data-theme-icon>{icon("moon")}</span></button>
</header>
<div class="layout">
<nav class="sidebar" aria-label="Main">
<div class="rail-group"><div class="rail-label">Work</div>{work}{conv_block}</div>
<div class="rail-group"><div class="rail-label">Records</div>{records}</div>
<div class="rail-foot">
<a href="/settings?folder={fq}" class="{settings_active}"><span class="icon">{icon("settings")}</span> Settings</a>
<a href="/?folder={fq}"><span class="icon">{icon("folder-add")}</span> New charter</a>
</div></nav>
<main class="main content">{inner}</main></div>
<div id="palette" role="dialog" aria-modal="true" aria-label="Command palette">
<div class="card glass"><input id="palInput" type="text" placeholder="Search or run a command…" oninput="palFilter(this.value)" aria-label="Commands">
<div id="palList" class="stack">
<button type="button" class="btn btn-ghost" onclick="location.href='/search?folder={fq}'"><span class="icon">{icon("search")}</span> Search the file index</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/review?folder={fq}'"><span class="icon">{icon("check")}</span> Approve all</button>
<button type="button" class="btn btn-ghost" onclick="undoLast()"><span class="icon">{icon("undo")}</span> Undo last move</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/ask?folder={fq}'"><span class="icon">{icon("ask")}</span> Ask the folder</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/outputs?folder={fq}'"><span class="icon">{icon("outputs")}</span> Rebuild outputs</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/settings?folder={fq}'"><span class="icon">{icon("settings")}</span> Settings</button>
<button type="button" class="btn btn-ghost" onclick="closePalette()"><span class="icon">{icon("close")}</span> Close</button></div></div></div>
<script src="/static/app.js"></script></body></html>"""


def page_head(title: str, sub: str = "", actions: str = "") -> str:
    return (f'<div class="page-head"><div><h1>{title}</h1>'
            f'{f"<p class=\"sub\">{sub}</p>" if sub else ""}</div>'
            f'{f"<div class=\"actions\">{actions}</div>" if actions else ""}</div>')


def empty_state(name: str, title: str, body: str, action: str = "") -> str:
    return (f'<div class="card empty"><div class="glyph" aria-hidden="true">{icon(name, 28)}</div>'
            f'<h3>{title}</h3><p>{body}</p>{action}</div>')


@app.get("/", response_class=HTMLResponse)
def setup(folder: str = "") -> Any:
    if folder:
        try:
            assert_not_protected(folder)
        except ProtectedPathError:
            return RedirectResponse(f"/protected?folder={quote(folder)}")
        if load_charter(folder) is not None:
            # Already set up: land on the live view (it shows whether it is watched)
            # instead of asking "What is this folder for?" all over again.
            return RedirectResponse(f"/overview?folder={quote(folder)}")
    initial = folder
    chips = "".join(f'<button type="button" class="chip" onclick="document.getElementById(\'purpose\').value={p!r}">{n}</button>'
                    for n, p in [("Student", "Lecture PDFs and study screenshots for my CS degree"),
                                 ("Freelancer", "Receipts and invoices I track for freelance taxes"),
                                 ("Data entry", "Data entry: extract name, phone, amount from each form")])
    mode_dd = dropdown("mode", [("suggest", "Suggest mode — nothing moves without you"),
                               ("auto", "Auto mode — move new files automatically")], "suggest")
    inner = f"""<div class="card setup-card">
<div class="setup-row"><span class="chip mono" title="{initial}">folder: <span id="fchip">{initial}</span></span>
<button type="button" class="btn" onclick="openPicker()"><span class="icon">{icon("folder", 16)}</span> Choose folder…</button></div>
<h1>What is this folder for?</h1>
<textarea id="purpose" rows="4" placeholder="Lecture PDFs and study screenshots…" aria-label="What is this folder for?"></textarea>
<div class="setup-row">
<button id="micBtn" class="mic-ring" onclick="toggleMic('purpose')" aria-label="Hold to talk">{icon("mic", 22)}</button>
<div class="chips">{chips}</div></div>
<div class="setup-row"><label class="label" for="mode">Mode</label>{mode_dd}</div>
<div class="setup-row"><input id="folder" type="text" class="manual-path" aria-label="Folder path"
 placeholder="Folder path" value="{initial}"></div>
<button class="btn btn-primary" onclick="createCharter()"><span class="icon">{icon("sparkles", 16)}</span> Create charter</button>
<div id="out" role="status" aria-live="polite"></div></div>
{folder_picker_html()}"""
    return shell("", "", inner)


@app.get("/protected", response_class=HTMLResponse)
def protected(folder: str = "", reason: str = "") -> str:
    inner = f"""<div class="card refusal" role="alert">
<div class="refusal-mark" aria-hidden="true">{icon("shield", 40)}</div>
<h1>Charta won't watch this folder</h1>
<p class="mono">{folder or '(no folder)'}</p>
<p>{reason or 'It is a system or profile location — like Windows, Program Files, AppData, a drive root, or your user folder root.'}</p>
<p>Nothing here was read, moved or changed. Pick a folder inside your documents instead —
for example <span class="mono">Documents/Receipts</span>.</p>
<button type="button" class="btn btn-primary" onclick="location.href='/'">Choose another folder</button>
</div>"""
    return shell("", folder, inner, label="Protected")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    if ICON.exists():
        return FileResponse(str(ICON), media_type="image/x-icon")
    return Response(status_code=404)


@app.get("/styleguide", response_class=HTMLResponse)
def styleguide() -> str:
    swatches = "".join(
        f'<span class="chip"><span class="dot" style="background:var(--{name})"></span>{name}</span>'
        for name in ["accent1", "success", "warning", "danger", "info"])
    icon_row = " ".join(f'<span class="icon" title="{n}">{icon(n, 20)}</span>'
                        for n in NAV_ITEMS + ["folder", "file", "undo", "shield", "search", "mic", "chevron-down"])
    inner = f"""{page_head("Styleguide", "Ink and paper. Every screen composes these tokens and components.")}
<section class="section"><div class="section-head"><h2 class="section-title">Colour</h2></div>
<div class="row">{swatches}</div></section>
<section class="section"><div class="section-head"><h2 class="section-title">Icons</h2></div>
<div class="row" style="gap:var(--s4)">{icon_row}</div></section>
<section class="section"><div class="section-head"><h2 class="section-title">Buttons</h2></div>
<div class="row"><button class="btn btn-primary"><span class="icon">{icon("sparkles", 16)}</span> Primary</button>
<button class="btn">Default</button><button class="btn btn-ghost">Ghost</button>
<button class="btn btn-icon" aria-label="Icon button">{icon("plus", 16)}</button></div></section>
<section class="section"><div class="section-head"><h2 class="section-title">Chips and badges</h2></div>
<div class="row"><div class="chip">chip</div>
<span class="chip pill-suggest">suggest</span><span class="chip pill-auto">auto</span>
<span class="badge-sensitive">sensitive</span></div></section>
<section class="section"><div class="section-head"><h2 class="section-title">States</h2></div>
<div class="row" style="align-items:flex-start"><div style="min-width:200px"><div class="conf"><span style="width:72%"></span></div>
<div class="skel" style="margin-top:var(--s3)">skeleton loader</div></div>
<div class="empty" style="padding:0"><div class="glyph">{icon("empty", 28)}</div>
<h3>Empty state</h3><p>Nothing here yet.</p><button class="btn">Next action</button></div></div></section>"""
    return shell("", "", inner, label="Styleguide")


def _page(folder: str, name: str) -> tuple[Any, str]:
    ch = load_charter(folder) if folder else None
    return ch, (ch.mode if ch else "suggest")


def mode_pill(mode: str) -> str:
    return ('<span class="chip pill-auto">Auto mode</span>' if mode == "auto"
            else '<span class="chip pill-suggest">Suggest mode</span>')


def mode_pill_class(mode: str) -> str:
    """The class of the mode chip (so a button can wear it)."""
    return "pill-auto" if mode == "auto" else "pill-suggest"


def _watch_controls(folder: str, ch: Any) -> str:
    """Watch/unwatch + rescan controls for a folder that has a charter."""
    if not ch or not folder:
        return ""
    if watchlist.is_watched(_cfg(), folder):
        return ('<span class="chip watching" title="Charta is watching this folder.">'
                f'<span class="icon">{icon("activity", 14)}</span> Watching</span>'
                f'<button class="btn" onclick="scanNow()"><span class="icon">{icon("scan", 16)}</span> Scan now</button>'
                f'<button class="btn btn-ghost" onclick="stopWatching()"><span class="icon">{icon("close", 16)}</span> Stop watching</button>')
    return (f'<button class="btn btn-primary" onclick="startWatching()">'
            f'<span class="icon">{icon("activity", 16)}</span> Watch this folder</button>')



def _provider_up() -> bool:
    """Reachability probe for the offline banner (short timeout, never raises).

    Long enough for a remote provider's TLS round trip (a 1s cap used to mark a
    working cloud endpoint as offline).
    """
    try:
        return LLMClient(_cfg()).ping(timeout=2.0)
    except Exception:  # noqa: BLE001
        return False


@app.get("/folders", response_class=HTMLResponse)
def folders_page(folder: str = "") -> str:
    """Every folder Charta knows about: watched, paused, and what is in them."""
    cfg = _cfg()
    entries = watchlist.load(cfg)
    cards: list[str] = []
    paused: list[str] = []
    watched_count = 0
    total_files = 0
    total_pending = 0
    total_gaps = 0

    for entry in entries:
        f = entry["folder"]
        if not pathlib.Path(f).exists():
            continue
        ch = load_charter(f)
        props = prop_store.load_proposals(f)
        pending = [p for p in props if p.status == "pending"]
        ai_gaps = load_ai_gaps(f)
        on_disk = _folder_files(f)
        total_files += len(on_disk)
        total_pending += len(pending)
        total_gaps += len(ai_gaps)
        is_watching = bool(entry.get("watching", True))
        if is_watching:
            watched_count += 1
        fid = "f" + str(abs(hash(f)) % 100000)
        facts = [("Files in folder", str(len(on_disk))),
                 ("Indexed", str(len(props))),
                 ("Waiting for review", str(len(pending))),
                 ("Model-noticed gaps", str(len(ai_gaps))),
                 ("Moves logged", str(len(journal_mod.entries(f)))),
                 ("Watching since", entry.get("added_at", "") or "—"),
                 ("Last scan", entry.get("last_scan", "") or "never")]
        facts_html = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)
        state_chip = ('<span class="chip watching"><span class="icon">'
                      f'{icon("activity", 14)}</span> Watching</span>' if is_watching
                      else '<span class="chip">Paused</span>')
        current_mode = ch.mode if ch else "suggest"
        other_mode = "auto" if current_mode == "suggest" else "suggest"
        mode_chip = (f'<button type="button" class="chip {mode_pill_class(current_mode)}" '
                     f'onclick="setMode({f!r}, {other_mode!r})" '
                     f'title="Switch this folder to {other_mode} mode">'
                     f'{mode_pill(current_mode)}</button>')
        purpose = ch.purpose if ch else "No charter yet — open the folder to set one up."
        ask_id = f"ask-{fid}"
        actions = [
            f'<a class="btn btn-primary" href="/overview?folder={quote(f)}">Open</a>',
            f'<a class="btn" href="/files?folder={quote(f)}">Files</a>',
            f'<a class="btn" href="/ask?folder={quote(f)}">Ask</a>',
            f'<button type="button" class="btn" onclick="scanFolder({f!r})">'
            f'<span class="icon">{icon("scan", 16)}</span> Scan now</button>',
        ]
        hist = history.summary(f)
        if hist.get("state") == "ready":
            actions.append(f'<a class="btn btn-ghost" href="/history?folder={quote(f)}">'
                           f'<span class="icon">{icon("history", 16)}</span> '
                           f'{escape_attr(hist.get("commits", "0"))} commits</a>')
        if is_watching:
            actions.append(f'<button type="button" class="btn btn-ghost" '
                           f'onclick="unwatchFolder({f!r})">Stop watching</button>')
        else:
            actions.append(f'<button type="button" class="btn btn-primary" '
                           f'onclick="watchFolder({f!r})">Resume watching</button>')
        card = f"""<div class="card fadein">
<div class="card-head"><h3>{_basename(f)}</h3><div class="row">{state_chip}{mode_chip}</div></div>
<p class="mono muted">{escape_attr(f)}</p>
<p class="muted">{escape_attr(purpose)}</p>
<dl class="facts">{facts_html}</dl>
<div class="row">{''.join(actions)}</div>
<div class="row" style="margin-top:var(--s3)">
<input id="{ask_id}-input" type="text" placeholder="Ask about this folder…" aria-label="Ask about {escape_attr(f)}">
<button type="button" class="btn" onclick="askIn({f!r}, {ask_id!r})">
<span class="icon">{icon("ask", 16)}</span> Ask</button></div>
<div id="{ask_id}"></div></div>"""
        (cards if is_watching else paused).append(card)

    if not entries:
        body = empty_state("folder-add", "No folders yet",
                           "Right-click a folder in Explorer and choose “Watch with Charta”, "
                           "or set one up from here.",
                           '<a class="btn btn-primary" href="/">Set up a folder</a>')
    else:
        body = f'<div class="stack">{"".join(cards)}</div>'

    strip = "".join(
        f'<div class="stat"><div class="n">{value}</div>'
        f'<div class="k"><span class="icon">{icon(ic, 15)}</span>{label}</div></div>'
        for value, label, ic in [
            (watched_count, _plural(watched_count, "folder watched", "folders watched"), "folder"),
            (total_files, _plural(total_files, "file in them", "files in them"), "stack"),
            (total_pending, _plural(total_pending, "waiting for review", "waiting for review"), "review"),
            (total_gaps, _plural(total_gaps, "gap the model noticed", "gaps the model noticed"), "gaps")])
    sub = (f"{watched_count} folder{'s' if watched_count != 1 else ''} watched, "
           f"{len(entries)} known in total.")
    sections = [f'<div class="stat-strip">{strip}</div>']
    if cards:
        sections.append(
            '<section class="section"><div class="section-head">'
            '<h2 class="section-title">Watched folders</h2>'
            '<span class="section-note">New files are analysed as they arrive.</span></div>'
            f'<div class="stack">{"".join(cards)}</div></section>')
    if paused:
        sections.append(
            '<section class="section"><div class="section-head">'
            '<h2 class="section-title">Paused</h2>'
            '<span class="section-note">Kept with their analysis — resume any time.</span></div>'
            f'<div class="stack">{"".join(paused)}</div></section>')
    inner = f"""{page_head("Folders", sub, f'<a class="btn btn-primary" href="/">'
                                f'<span class="icon">{icon("folder-add", 16)}</span> Add a folder</a>')}
<div id="scanProgress"></div>
{''.join(sections) if entries else body}"""
    return shell("folders", folder, inner)


def _folder_files(folder: str) -> list[pathlib.Path]:
    """Every real file in a watched folder (``.charta/`` is Charta's own)."""
    root = pathlib.Path(folder)
    if not root.exists():
        return []
    out: list[pathlib.Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if ".charta" in p.parts:
            continue
        out.append(p)
    return out


def escape_attr(text: str) -> str:
    """Escape a string for use inside an HTML attribute."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _plural(count: int, one: str, many: str) -> str:
    """Label that agrees with the number in front of it."""
    return f"{count} {one if count == 1 else many}"


@app.get("/files", response_class=HTMLResponse)
def files_page(folder: str = "") -> str:
    """What Charta has seen in this folder: every file, its index state, and a reader."""
    if not folder:
        return shell("files", folder, empty_state("stack", "No folder selected",
                                                 "Pick a watched folder to see the files inside it.",
                                                 '<a class="btn btn-primary" href="/folders">Open folders</a>'))
    ch, mode = _page(folder, "files")
    props = {p.source: p for p in prop_store.load_proposals(folder)}
    meta = index_db.file_meta(folder)
    rows: list[str] = []
    for path in _folder_files(folder):
        rel = str(path.relative_to(pathlib.Path(folder)))
        prop = props.get(rel)
        info = meta.get(rel, {})
        status = prop.status if prop else (info.get("description", "") and "indexed" or "not indexed")
        badge = '<span class="badge-sensitive">sensitive</span>' if (prop and prop.sensitive) else ""
        size = path.stat().st_size
        kind = path.suffix.lstrip(".").lower() or "file"
        tags = "".join(f'<span class="chip">{escape_attr(t)}</span>'
                       for t in info.get("tags", [])[:4])
        rows.append(
            f'<tr><td class="mono">{escape_attr(rel)}<div class="row" style="margin-top:var(--s1)">{tags}</div></td>'
            f'<td>{kind}</td><td>{size:,} B</td>'
            f'<td>{escape_attr(str(status))}</td>'
            f'<td class="muted">{escape_attr(prop.reason) if prop else escape_attr(info.get("description", ""))} {badge}</td>'
            f'<td class="row"><button type="button" class="btn btn-ghost" '
            f'onclick="readFile({folder!r}, {rel!r})">Read</button>'
            f'<button type="button" class="btn btn-ghost" '
            f'onclick="editFile({folder!r}, {rel!r})">Edit</button>'
            f'<button type="button" class="btn btn-ghost" '
            f'onclick="openFile({folder!r}, {rel!r})">Open</button>'
            f'<button type="button" class="btn btn-ghost" '
            f'onclick="trashFile({folder!r}, {rel!r})">Move to trash</button></td></tr>')
    if rows:
        table = (f'<table class="grid"><thead><tr><th>File</th><th>Kind</th><th>Size</th>'
                 f'<th>Index state</th><th>Why</th><th></th></tr></thead>'
                 f'<tbody>{"".join(rows)}</tbody></table>')
    else:
        table = empty_state("empty", "Nothing here yet",
                            "Drop files into this folder and Charta will index them.",
                            f'<button type="button" class="btn" onclick="scanFolder({folder!r})">'
                            f'<span class="icon">{icon("scan", 16)}</span> Scan now</button>')
    trashed = tools.trash_listing(folder)
    if trashed:
        trash_rows = "".join(
            f'<div class="row-item"><div class="row"><span class="mono">{escape_attr(t["path"])}</span>'
            f'<span class="spacer"></span>'
            f'<button type="button" class="btn btn-ghost" '
            f'onclick="restoreFile({folder!r}, {t["path"]!r})">Bring back</button></div>'
            f'<p class="muted">Was {escape_attr(t["was"] or "unknown")} — nothing is ever deleted.</p></div>'
            for t in trashed)
        trash_section = ('<section class="section"><div class="section-head">'
                         '<h2 class="section-title">In Charta\'s trash</h2>'
                         '<span class="section-note">Moved aside, never deleted. Bring any of them back.</span>'
                         f'</div><div class="card"><div class="log">{trash_rows}</div></div></section>')
    else:
        trash_section = ""
    inner = f"""{page_head("Files", "Every file Charta has seen in this folder, and what it thinks of it.",
                          f'<button type="button" class="btn" onclick="scanFolder({folder!r})">'
                          f'<span class="icon">{icon("scan", 16)}</span> Scan now</button>')}
<div id="scanProgress"></div>
<div class="card">{table}</div>
<div id="reader"></div>
{trash_section}"""
    return shell("files", folder, inner, mode)


@app.get("/history", response_class=HTMLResponse)
def history_page(folder: str = "") -> str:
    """The folder's private history: what Charta changed, when, and why."""
    if not folder:
        return shell("history", folder, empty_state(
            "history", "No folder selected",
            "Pick a watched folder to see its history.", ""))
    _, mode = _page(folder, "history")
    commits = history.log(folder, 60)
    if not history.available():
        body = empty_state("history", "No git on this machine",
                           "Charta keeps a private history of every folder it changes. "
                           "Install git and scan the folder to start one.")
    elif not commits:
        body = empty_state("history", "No history yet",
                           "Charta records every index, move and rebuild here — "
                           "scan the folder to start the trail.",
                           f'<button type="button" class="btn" onclick="scanFolder({folder!r})">'
                           f'<span class="icon">{icon("scan", 16)}</span> Scan now</button>')
    else:
        rows = []
        for c in commits:
            files = c.get("files", "")
            listed = "".join(
                f'<li class="mono"><span>{escape_attr(f)}</span></li>'
                for f in [x.strip() for x in files.split(",") if x.strip()][:12])
            rows.append(
                f'<div class="row-item"><div class="row">'
                f'<span class="mono muted">{c["date"]}</span>'
                f'<span class="mono">{c["sha"][:8]}</span>'
                f'<span class="spacer"></span>'
                f'<span class="chip">{c.get("count", "0")} file(s)</span></div>'
                f'<p>{escape_attr(c["message"])}</p>'
                f'<ul class="muted" style="margin:var(--s2) 0 0;padding-left:var(--s5)">{listed}</ul>'
                f'</div>')
        body = f'<div class="card"><div class="log">{"".join(rows)}</div></div>'
    inner = f"""{page_head("History", "Charta's own record of this folder — a private git history in .charta/git.")}
{body}"""
    return shell("history", folder, inner, mode)


@app.post("/api/history/restore")
def api_history_restore(folder: str, sha: str, path: str) -> JSONResponse:
    """Put an old version of one file back (a copy — the current file is kept)."""
    bad = _guard(folder)
    if bad:
        return bad
    root = pathlib.Path(folder).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or ".charta" in target.parts:
        return JSONResponse({"error": "outside-folder",
                              "message": "Charta only restores files inside the folder."},
                             status_code=400)
    restored = history.restore_file(root, sha, path)
    if not restored:
        return JSONResponse({"error": "missing", "message": "That version is not in the history."},
                             status_code=404)
    record.record(_cfg(), folder, f"charta: restored {path} from {sha[:8]}")
    return JSONResponse({"restored": path})


@app.get("/api/file/trash")
def api_trash_list(folder: str) -> JSONResponse:
    """What is in this folder's trash (nothing is ever truly deleted)."""
    bad = _guard(folder)
    if bad:
        return bad
    return JSONResponse({"items": tools.trash_listing(folder)})


@app.post("/api/file/write")
async def api_file_write(folder: str, req: Request) -> JSONResponse:
    """Write a text file inside the folder, keeping the old version."""
    bad = _guard(folder)
    if bad:
        return bad
    body = await req.json()
    try:
        result = tools.write(folder, str(body.get("path", "")), str(body.get("text", "")))
    except tools.ToolError as e:
        return JSONResponse({"error": "tool-error", "message": str(e)}, status_code=400)
    record.record(_cfg(), folder, f"charta: edited {result['path']}")
    return JSONResponse(result)


@app.post("/api/file/trash")
async def api_file_trash(folder: str, req: Request) -> JSONResponse:
    """Move a file to the folder's trash — it can always be brought back."""
    bad = _guard(folder)
    if bad:
        return bad
    body = await req.json()
    try:
        result = tools.trash(folder, str(body.get("path", "")))
    except tools.ToolError as e:
        return JSONResponse({"error": "tool-error", "message": str(e)}, status_code=400)
    record.record(_cfg(), folder,
                  f"charta: moved {result['from']} to the trash (not deleted)")
    return JSONResponse(result)


@app.post("/api/file/restore")
async def api_file_restore(folder: str, req: Request) -> JSONResponse:
    """Bring a file back from the trash."""
    bad = _guard(folder)
    if bad:
        return bad
    body = await req.json()
    try:
        result = tools.restore(folder, str(body.get("path", "")))
    except tools.ToolError as e:
        return JSONResponse({"error": "tool-error", "message": str(e)}, status_code=400)
    record.record(_cfg(), folder, f"charta: restored {result['restored']} from the trash")
    return JSONResponse(result)


@app.post("/api/mode")
def api_mode(folder: str, mode: str = "") -> JSONResponse:
    """Switch one folder between suggest and auto mode (opt-in, per folder).

    Auto mode moves new files as they arrive. Suggest mode only proposes.
    """
    bad = _guard(folder)
    if bad:
        return bad
    if mode not in ("suggest", "auto"):
        return JSONResponse({"error": "bad-mode", "message": "Mode must be suggest or auto."},
                             status_code=400)
    ch = load_charter(folder)
    if ch is None:
        return JSONResponse({"error": "no-charter", "message": "Create a charter first."},
                             status_code=400)
    ch.mode = mode
    ch.updated = ""
    save_charter(pathlib.Path(folder), ch)
    return JSONResponse({"mode": mode, "folder": folder})


@app.get("/api/search")
def api_search(q: str = "", folder: str = "") -> JSONResponse:
    """Search the metadata index: names, tags, descriptions, fields and text.

    With no folder it searches every watched folder and says which one each
    result came from.
    """
    query = str(q or "").strip()
    if not query:
        return JSONResponse({"query": "", "results": [], "folders": []})
    cfg = _cfg()
    targets = [folder] if folder else watchlist.folders(cfg)
    results: list[dict] = []
    for target in targets:
        if not target:
            continue
        for item in index_db.search(target, query, limit=25):
            item = dict(item)
            item["folder"] = target
            item["folder_name"] = _basename(target)
            results.append(item)
    results.sort(key=lambda i: -i.get("score", 0))
    return JSONResponse({"query": query, "results": results[:60],
                         "folders": [_basename(t) for t in targets if t]})


@app.get("/search", response_class=HTMLResponse)
def search_page(q: str = "", folder: str = "") -> str:
    """Search the folder's index. Results are files, with their metadata."""
    cfg = _cfg()
    query = str(q or "").strip()
    fq = quote(folder)
    scope = folder or ""
    if not scope:
        scope = watchlist.folders(cfg)[0] if watchlist.folders(cfg) else ""
    results: list[dict] = []
    if query and scope:
        results = index_db.search(scope, query, limit=40)
    rows = ""
    for item in results:
        tags = "".join(f'<span class="chip">{escape_attr(t)}</span>' for t in item.get("tags", [])[:6])
        fields = item.get("fields", {})
        facts = "".join(f"<dt>{escape_attr(k)}</dt><dd>{escape_attr(str(v))}</dd>"
                        for k, v in fields.items() if v)
        rows += f"""<div class="card fadein"><div class="row">
<span class="icon">{icon('file', 20)}</span>
<div style="flex:1;min-width:0">
<p class="mono">{escape_attr(item['path'])}</p>
<p class="muted">{escape_attr(item.get('description', ''))}</p>
<div class="row">{tags}{f'<span class="chip pill-suggest">{escape_attr(item.get("doc_type", "document"))}</span>'}</div>
<dl class="facts">{facts}</dl>
</div>
<div class="row">
<a class="btn" href="/files?folder={fq}">Open</a>
<button type="button" class="btn btn-ghost" onclick="readFile({scope!r}, {item['path']!r})">Read</button>
<button type="button" class="btn btn-ghost" onclick="openFile({scope!r}, {item['path']!r})">Open in app</button>
<button type="button" class="btn btn-ghost" onclick="askAbout({scope!r}, {item['path']!r})">Ask about it</button>
</div></div></div>"""
    if not query:
        body = empty_state("search", "Search the index",
                           "Charta keeps a metadata index of every file it has read — "
                           "type a word, a tag, a vendor or an amount.",
                           f'<div class="row"><input id="q" type="text" placeholder="sponsorship 2026" '
                           f'aria-label="Search" onkeydown="if(event.key===\'Enter\')'
                           f'location.href=\'/search?folder={fq}&q=\'+encodeURIComponent(this.value)">'
                           f'<button class="btn btn-primary" onclick="location.href='
                           f"'/search?folder={fq}&q='+encodeURIComponent(document.getElementById('q').value)\">"
                           f'<span class="icon">{icon("search", 16)}</span> Search</button></div>')
    elif not results:
        body = empty_state("empty", "Nothing found",
                           f"No file in {scope} matches that. Try a vendor, a year or an amount.")
    else:
        body = f'<div class="stack">{rows}</div>'
    index_note = ""
    if scope:
        st = index_db.stats(scope)
        index_note = (f'<span class="section-note">Index: {st["files"]} file(s), '
                      f'{st["chunks"]} chunk(s)</span>')
    inner = f"""{page_head("Search", "Find files by name, tag, description or content.",
                          f'<span class="chip">{_basename(scope) if scope else "no folder"}</span>')}
<div class="row"><input id="q" type="text" placeholder="sponsorship 2026" aria-label="Search" value="{escape_attr(query)}"
 onkeydown="if(event.key==='Enter')location.href='/search?folder={fq}&q='+encodeURIComponent(this.value)">
<button class="btn btn-primary" onclick="location.href='/search?folder={fq}&q='+encodeURIComponent(document.getElementById('q').value)">
<span class="icon">{icon("search", 16)}</span> Search</button></div>
{index_note}
{body}
<div id="reader"></div>"""
    return shell("search", folder, inner)


@app.post("/api/file/open")
async def api_file_open(folder: str, req: Request) -> JSONResponse:
    """Open a file with the system's default app (PDF viewer, editor…)."""
    bad = _guard(folder)
    if bad:
        return bad
    body = await req.json()
    try:
        target = tools.resolve(folder, str(body.get("path", "")))
    except tools.ToolError as e:
        return JSONResponse({"error": "tool-error", "message": str(e)}, status_code=400)
    if not tools.open_in_system(target):
        return JSONResponse({"error": "could-not-open",
                             "message": "Could not open that file here."}, status_code=500)
    return JSONResponse({"opened": str(target.name)})


@app.post("/api/file/reveal")
async def api_file_reveal(folder: str, req: Request) -> JSONResponse:
    """Show a file in Explorer / the file manager."""
    bad = _guard(folder)
    if bad:
        return bad
    body = await req.json()
    try:
        target = tools.resolve(folder, str(body.get("path", "")))
    except tools.ToolError as e:
        return JSONResponse({"error": "tool-error", "message": str(e)}, status_code=400)
    if not tools.reveal_in_file_manager(target):
        return JSONResponse({"error": "could-not-open",
                             "message": "Could not show that file."}, status_code=500)
    return JSONResponse({"revealed": str(target.name)})


@app.get("/overview", response_class=HTMLResponse)
def overview(folder: str = "") -> str:
    ch, mode = _page(folder, "overview")
    if folder and ch is None:
        return shell("overview", folder, "<h1>Protected or unknown folder</h1><p>No charter found. Create one from setup.</p>", mode)
    props = prop_store.load_proposals(folder) if folder else []
    pend = [p for p in props if p.status == "pending"]
    on_disk = _folder_files(folder) if folder else []
    ai_gaps = load_ai_gaps(folder) if folder else []
    fq = quote(folder)
    purpose = ch.purpose if ch else "no charter yet"
    offline = "" if _provider_up() else (
        f'<div class="banner warn"><span class="icon">{icon("alert", 16)}</span><span>The AI engine is offline, so '
        'classification falls back to built-in rules. Start it, then reload.</span>'
        '<span class="spacer"></span><a class="btn" href="/settings">Settings</a></div>')
    stats = "".join(
        f'<div class="stat"><div class="n">{value}</div>'
        f'<div class="k"><span class="icon">{icon(ic, 15)}</span>{label}</div></div>'
        for value, label, ic in [
            (len(props), "files tracked", "stack"),
            (len(pend), "waiting for review", "review"),
            (len(ai_gaps), f"{'gap' if len(ai_gaps) == 1 else 'gaps'} the model noticed", "gaps"),
            (len(journal_mod.entries(folder)) if folder else 0, "moves logged", "activity")])
    next_action = (f'<a class="btn btn-primary" href="/review?folder={fq}"><span class="icon">{icon("review", 16)}</span> Review {len(pend)}</a>'
                   if pend else f'<a class="btn" href="/outputs?folder={fq}"><span class="icon">{icon("outputs", 16)}</span> Open outputs</a>')
    watching = bool(folder) and ch is not None and watchlist.is_watched(_cfg(), folder)
    empty = watching and not on_disk
    if empty:
        scanning_note = ('<p class="section-note">This folder is empty. Charta is watching it — '
                          'drop files in and they will be analysed and sorted.</p>')
    elif watching and not props:
        scanning_note = ('<p class="section-note">Charta is scanning this folder now — '
                         'refresh in a moment, or press <em>Scan now</em>.</p>')
    else:
        scanning_note = ""
    waiting = (f'{len(pend)} proposal waiting for you' if pend == 1
               else f'{len(pend)} proposals waiting for you' if pend
               else 'Nothing waiting — you are up to date.')
    inner = f"""{page_head("Overview", purpose, _watch_controls(folder, ch) + next_action)}
{offline}<div class="stat-strip">{stats}</div>{scanning_note}
<section class="section"><div class="section-head">
<h2 class="section-title">Needs your review</h2>
<div class="section-actions">{mode_pill(mode)}
<a class="btn" href="/review?folder={fq}"><span class="icon">{icon("review", 16)}</span> Open review</a></div></div>
<p class="section-note">{waiting}</p></section>
<section class="section"><div class="section-head">
<h2 class="section-title">Gaps the model noticed</h2>
<div class="section-actions"><a class="btn" href="/gaps?folder={fq}"><span class="icon">{icon("gaps", 16)}</span> View gaps</a></div></div>
<p class="section-note">{'; '.join(g['note'] for g in ai_gaps[:3]) or 'Nothing yet — these appear when Ask notices something is missing.'}</p></section>
<section class="section"><div class="section-head">
<h2 class="section-title">Latest outputs</h2>
<div class="section-actions"><a class="btn" href="/outputs?folder={fq}"><span class="icon">{icon("outputs", 16)}</span> View outputs</a></div></div>
<p class="section-note">Spreadsheet, notes and flashcards built from this folder.</p></section>"""
    return shell("overview", folder, inner, mode)


@app.get("/review", response_class=HTMLResponse)
def review(folder: str = "") -> str:
    _, mode = _page(folder, "review")
    props = prop_store.load_proposals(folder) if folder else []
    fq = quote(folder)
    pending = [p for p in props if p.status == "pending"]
    if not pending:
        return shell("review", folder, page_head("Review", "Nothing is moved until you approve it.")
                     + empty_state("check", "All clear", "No proposals waiting. Drop a file into the folder and "
                                    "Charta will suggest where it belongs.",
                                    f'<a class="btn" href="/overview?folder={fq}"><span class="icon">{icon("overview", 16)}</span> Back to overview</a>'), mode)
    cards = ""
    for p in pending:
        sens = '<span class="badge-sensitive">sensitive</span>' if p.sensitive else ""
        cards += f"""<div class="card prop-card fadein" data-src="{escape_attr(p.source)}"><div class="prop">
<span class="thumb" aria-hidden="true">{icon("file", 20)}</span><div style="flex:1;min-width:0">
<div class="mono">{p.source} <span class="dest">→ {p.dest_dir}/{p.new_name}</span></div>
<div class="conf" role="img" aria-label="confidence {int(p.confidence*100)} percent"><span style="width:{int(p.confidence*100)}%"></span></div>
<p class="reason">{p.reason}</p>{sens}
<div class="row"><button class="btn btn-primary" onclick="approveOne({p.source!r})"><span class="icon">{icon("check", 16)}</span> Approve <span class="kbd">A</span></button>
<button class="btn" onclick="rejectOne({p.source!r})"><span class="icon">{icon("close", 16)}</span> Reject <span class="kbd">R</span></button>
<button class="btn btn-ghost" onclick="toast({p.reason!r},false)"><span class="icon">{icon("info", 16)}</span> Why?</button></div>
</div></div></div>"""
    tree = ("<div class='tree'>" + icon("folder", 15) + " " + (folder or ".") + "<br>"
            + "<br>".join("└─ " + p.dest_dir + "/" + p.new_name for p in pending[:8]) + "</div>")
    approve_all = (f"fetch('/api/approve?folder={fq}',{{method:'POST',headers:{{'Content-Type':'application/json'}},"
                   "body:JSON.stringify({all:true})}).then(()=>location.reload())")
    inner = f"""{page_head("Review", f"{len(pending)} waiting. Nothing moves until you approve it.",
        f'<button class="btn" onclick="undoLast()"><span class="icon">{icon("undo", 16)}</span> Undo last move</button>'
        f'<button class="btn btn-primary" onclick="{approve_all}"><span class="icon">{icon("check", 16)}</span> Approve all</button>')}
<div class="legend"><span><span class="kbd">J</span>/<span class="kbd">K</span> move</span>
<span><span class="kbd">A</span> approve</span><span><span class="kbd">R</span> reject</span>
<span><span class="kbd">Esc</span> close</span></div>
<div class="stack">{cards}</div>
<section class="section"><div class="section-head">
<h2 class="section-title">Proposed structure</h2>
<span class="section-note">Where files would land after approval</span></div>
{tree}</section>"""
    return shell("review", folder, inner, mode)


@app.get("/outputs", response_class=HTMLResponse)
def outputs(folder: str = "") -> str:
    ch, mode = _page(folder, "outputs")
    inner = f"""{page_head("Outputs", (ch.purpose if ch else "What this folder can become: a spreadsheet, notes, flashcards and tables."))}
<div class="outgrid">{''.join(
    f'''<div class="card outcard" data-kind="{kind}" data-folder="{escape_attr(folder)}">
<div class="card-head"><h3><span class="icon">{icon(info["ic"], 16)}</span> {info["title"]}</h3>
<span class="chip outstate" id="state-{kind}"></span></div>
<p class="muted">{info["desc"]}</p>
<div class="outmeta muted mono" id="meta-{kind}"></div>
<div class="outpreview" id="prev-{kind}"></div>
<div class="row" style="margin-top:var(--s3)">
<button type="button" class="btn" onclick="outShow(this)"><span class="icon">{icon("folder-open", 16)}</span> Show file</button>
<button type="button" class="btn btn-ghost" onclick="outRebuild(this)"><span class="icon">{icon("scan", 16)}</span> Rebuild</button>
<button type="button" class="btn btn-ghost" onclick="outToggle(this)"><span class="icon">{icon("empty", 16)}</span> Hide preview</button>
</div></div>''' for kind, info in OUTPUT_KINDS.items())}</div>"""
    return shell("outputs", folder, inner, mode)


@app.get("/gaps", response_class=HTMLResponse)
def gaps(folder: str = "") -> str:
    _ch, mode = _page(folder, "gaps")
    fq = quote(folder)
    items = load_ai_gaps(folder) if folder else []
    rows = "".join(
        f'<div class="row-item"><div class="row"><span class="icon">'
        f'{icon("gaps", 16)}</span><span>{escape_attr(g["note"])}</span>'
        f'<span class="spacer"></span><span class="caption mono">{escape_attr(g.get("at", ""))}</span></div></div>'
        for g in items)
    if not rows:
        body = empty_state("gaps", "Nothing missing — yet",
                           "When the model notices the folder is missing something while "
                           "answering (e.g. \"no bill for March\"), it shows up here. Gaps "
                           "come from the AI, not from an automated check.",
                           f'<a class="btn" href="/ask?folder={fq}"><span class="icon">{icon("sparkles", 16)}</span> Ask about this folder</a>')
    else:
        body = f'<div class="card">{rows}</div>'
    inner = f"""{page_head("Gaps", "What the model noticed is missing — only it proposes these.")}
{body}"""
    return shell("gaps", folder, inner, mode)


@app.get("/ask", response_class=HTMLResponse)
def ask_page(folder: str = "", q: str = "", chat: str = "") -> str:
    ch, mode = _page(folder, "ask")
    fq = quote(folder)
    cfg = _cfg()
    if not folder:
        # Asking always means asking about *one* folder. Offer the watched ones
        # instead of silently searching whatever the app is sitting in.
        watched = watchlist.folders(cfg)
        choices = "".join(
            f'<a class="btn" href="/ask?folder={quote(f)}">'
            f'<span class="icon">{icon("folder", 16)}</span> {_basename(f)}</a>' for f in watched)
        body = empty_state(
            "ask", "Which folder?",
            "Charta answers about one folder at a time — pick the one you mean.",
            choices or '<a class="btn btn-primary" href="/folders">Open folders</a>')
        inner = f"""{page_head("Ask", "Answers cite file and page. If it is not in the folder, Charta says so.")}
{body}"""
        return shell("ask", folder, inner, mode)
    # starter cards: what this folder is made for always comes first
    starter_specs = [("folder", "What is in this folder?",
                      "An inventory of everything here, with a purpose for it"),
                     ("sparkles", "Summarise the newest files",
                      "What just arrived, in a few lines")]
    if ch and ch.expected:
        starter_specs.append(("search", f"What about {ch.expected[0]}?",
                              "The first item the charter expects to find"))
    starter_specs.append(("alert", "What is missing here?",
                          "Expected items that have not shown up yet"))
    starters = "".join(
        f'<button type="button" class="starter" onclick="askFolder({t!r})">'
        f'<span class="starter-icon icon">{icon(ic, 18)}</span>'
        f'<span class="starter-body"><span class="starter-t">{t}</span>'
        f'<span class="starter-d">{d}</span></span></button>'
        for ic, t, d in starter_specs)
    runs_chip = (f'<span class="chip" title="Where the answers come from.">'
                 f'<span class="icon">{icon("shield" if cfg.llm_provider in LOCAL_PROVIDERS else "info", 14)}</span>'
                 f'{cfg.generation_model}</span>')
    inner = f"""<div class="askwrap">
<section class="chatpane" id="chatpane">
<div class="hero"><span class="hero-mark icon">{icon("sparkles", 22)}</span>
<h1>What do you want to know about {_basename(folder)}?</h1>
<p class="sub muted">Answers cite the file and page they came from, every follow-up
remembers what you asked before, and nothing leaves your machine.</p></div>
<div class="chatscroll"><div class="chatlog" id="log" role="log" aria-live="polite"></div></div>
<div class="composerbox"><form class="composer" onsubmit="return chartaAskSubmit(event)">
<textarea id="q" class="qbox" rows="1" aria-label="Your question"
placeholder="Ask about this folder — e.g. What electricity bills do we have for March?">{escape_attr(q)}</textarea>
<div class="composer-row"><div class="row">
<button type="button" class="btn btn-ghost btn-icon" onclick="toggleMic('q')" aria-label="Ask by voice">{icon("mic", 18)}</button>
{runs_chip}</div><div class="row">
<button type="button" class="chip" onclick="copyDiag()">Copy diagnostics</button>
<button type="submit" class="sendbtn" aria-label="Ask">{icon("arrow-right", 18)}</button></div></div>
</form>
<p class="composer-meta muted">Copy diagnostics if an answer never arrives.
<span class="mono">code {_code_revision()} · backend {_STARTED}</span></p></div>
<div class="starters" aria-label="Try asking">{starters}</div>
</section></div>"""
    scripts = []
    if chat.strip() and re.fullmatch(r"[A-Za-z0-9-]+", chat):
        scripts.append(f"openChat({chat.strip()!r})")
    if q.strip():
        scripts.append(f"askFolder({q.strip()!r})")
    if scripts:
        inner += ('<script>window.addEventListener("load",()=>{'
                  + ";".join(scripts) + ';});</script>')
    return shell("ask", folder, inner, mode)


@app.get("/activity", response_class=HTMLResponse)
def activity(folder: str = "") -> str:
    _, mode = _page(folder, "activity")
    entries = list(reversed(journal_mod.entries(folder))) if folder else []
    rows = "".join(
        f'<div class="row-item"><div class="row"><span class="caption mono">{e.get("ts", "")}</span>'
        f'<span class="spacer"></span><button class="btn btn-ghost" onclick="undoLast()"><span class="icon">{icon("undo", 16)}</span> Undo</button></div>'
        f'<p class="mono">{e.get("src", "")} → {e.get("dst", "")}</p>'
        f'<p class="muted">{e.get("reason", "")}</p></div>'
        for e in entries)
    if not rows:
        body = empty_state("history", "No activity yet",
                           "Every move lands here with the reason it was made, and each one can be undone.")
    else:
        body = f'<div class="card"><div class="log">{rows}</div></div>'
    inner = f"""{page_head("Activity", "Every change Charta made, newest first.")}
{body}"""
    return shell("activity", folder, inner, mode)


@app.get("/settings", response_class=HTMLResponse)
def settings(folder: str = "", req: Request = None) -> str:  # type: ignore[assignment]
    cfg = _cfg()
    up = LLMClient(cfg).ping()
    from ..voice import stt as stt_mod
    from ..core.config import PROVIDER_BASE_URLS as _PBU
    # Editable options for the two dropdowns; availability shown inline so the
    # user can see at a glance why a provider may refuse.
    PROVIDERS_UI = sorted(_PBU) + ["custom"]
    VOICES_UI: list[tuple[str, str]] = []
    for p in stt_mod.PROVIDERS:
        ok = stt_mod.cloud_label(p) or stt_mod.backend_available(p)
        VOICES_UI.append((p, stt_mod.provider_label(p)
                          + ("" if ok else " — not installed")))
    voice_cloud = stt_mod.cloud_label(cfg.voice_provider)
    # Where did the LLM key come from? Only a key stored in config.toml is
    # editable from the UI (an env key still shows, but is env's business).
    doc = load_document(config_path())
    key_from_file = bool(str(doc.get("llm", {}).get("api_key", "")).strip())
    # The backend cannot otherwise know which shell is hosting the UI.
    user_agent = (req.headers.get("user-agent", "") if req else "")
    shell_kind = "Electron desktop" if "Electron" in user_agent else "browser"
    inner = f"""{page_head("Settings", "Everything here lives in config.toml on your machine — saved straight from this page.")}
<form id="settingsform" onsubmit="return saveSettings(event)">
<section class="section"><div class="section-head">
<h2 class="section-title"><span class="icon">{icon("sparkles", 16)}</span> AI provider</h2>
<span class="chip {'pill-suggest' if up else 'pill-auto'}">{'healthy' if up else 'offline'}</span></div>
<dl class="facts facts-form">
<dt>Provider</dt><dd>{dropdown("st-llm-provider", [(p, p) for p in PROVIDERS_UI], cfg.llm_provider)}</dd>
<dt>Base URL</dt><dd><input name="st-llm-base_url" class="qbox" type="text"
      value="{cfg.llm_base_url}" placeholder="http://localhost:11434/v1"
      spellcheck="false" autocomplete="off">
    <span class="muted">left alone when you pick a provider with a stock endpoint</span></dd>
<dt>API key</dt><dd class="keyrow"><input id="st-llm-api_key" name="st-llm-api_key" class="qbox keyin" type="password"
      placeholder="{'stored — type a new key to replace it' if key_from_file else 'paste a key (or leave empty and use CHARTA_API_KEY)'}"
      autocomplete="off">{'<button type="button" class="btn tiny-btn" onclick="clearKey(this)">Clear</button>' if key_from_file else ''}</dd>
<dt>Generation model</dt><dd><input name="st-llm-generation" class="qbox" type="text"
      value="{cfg.generation_model}" spellcheck="false" autocomplete="off"></dd>
<dt>Vision model</dt><dd><input name="st-llm-vision_model" class="qbox" type="text"
      value="{cfg.vision_model}" placeholder="same as generation when empty"
      spellcheck="false" autocomplete="off"></dd>
<dt>Read images</dt><dd><label class="checkline"><input type="checkbox" name="st-llm-vision"
      {'checked' if cfg.vision else ''}> use the vision model for scanned PDFs and screenshots</label></dd>
<dt>Timeout · retries</dt><dd class="keyrow">
    <input name="st-llm-timeout_seconds" class="qbox numin" type="number" min="5" max="600"
           value="{cfg.llm_timeout}">s
    <input name="st-llm-retries" class="qbox numin" type="number" min="0" max="5"
           value="{cfg.llm_retries}">tries</dd>
</dl>
<div class="row" style="margin-top:var(--s4)"><button class="btn" onclick="location.reload()"><span class="icon">{icon("undo", 16)}</span> Check again</button>
<a class="btn" href="/styleguide?folder={quote(folder)}">Design tokens</a></div>
<p class="muted">Any OpenAI-compatible endpoint works: Ollama, LM Studio, llama.cpp, vLLM,
OpenRouter, Groq… A cloud provider here is a deliberate choice — it is labelled at the top
of the window. <code>charta doctor</code> prints the full report; the log is at <code>{applog.log_path(cfg)}</code>.</p></section>
<section class="section"><div class="section-head">
<h2 class="section-title"><span class="icon">{icon("mic", 16)}</span> Voice — speech to text</h2>
<span class="chip" id="voice-cloudchip">{'cloud — audio leaves this device' if voice_cloud else 'on-device'}</span></div>
<dl class="facts facts-form">
<dt>Provider</dt><dd>{dropdown("st-voice-provider", VOICES_UI, cfg.voice_provider)}</dd>
<dt>Whisper model</dt><dd><input name="st-voice-whisper_model" class="qbox" type="text"
      value="{cfg.whisper_model}" placeholder="small" spellcheck="false" autocomplete="off"></dd>
<dt>Moonshine model</dt><dd><input name="st-voice-stt_model" class="qbox" type="text"
      value="{cfg.stt_model}" placeholder="moonshine-base-ONNX" spellcheck="false" autocomplete="off"></dd>
<dt>ElevenLabs key</dt><dd class="keyrow"><input id="st-voice-api_key" name="st-voice-api_key" class="qbox keyin" type="password"
      placeholder="{'stored — type a new key to replace it' if cfg.voice_api_key else 'needed only for the cloud provider'}"
      autocomplete="off">{'<button type="button" class="btn tiny-btn" onclick="clearKey(this)">Clear</button>' if cfg.voice_api_key else ''}</dd>
</dl>
<p class="muted" id="voice-hint"><b>Ctrl+Space</b> anywhere in the app opens the voice popup: hold
to speak, release to ask. In the desktop window it works even when Charta sits in the tray.
Moonshine runs on a tiny local model (install: <code>pip install useful-moonshine-onnx</code>);
System speech uses Windows' built-in engine; ElevenLabs is cloud and optional.</p></section>
<div class="savebar"><button type="submit" class="btn solid"><span class="icon">{icon("check", 16)}</span> Save settings</button>
<span class="muted">written to <code>{config_path()}</code> · git-ignored, machine-local</span></div>
</form>
<section class="section"><div class="section-head">
<h2 class="section-title"><span class="icon">{icon("folders", 16)}</span> Folders</h2>
<span class="chip">{len(watchlist.folders(cfg))} watched</span></div>
<dl class="facts">
<dt>Watched folders</dt><dd class="mono">{watchlist.registry_path(cfg)}</dd>
<dt>Known folders</dt><dd>{len(watchlist.known(cfg))} ({len(watchlist.folders(cfg))} being watched)</dd>
<dt>History</dt><dd>{'on — a private git history in each folder' if cfg.history and history.available() else 'off'}</dd>
</dl>
<p class="muted">This file remembers every folder you have set up, so Charta picks up where it left off
the next time you open it. Paused folders keep their analysis.</p></section>
<section class="section"><div class="section-head">
<h2 class="section-title"><span class="icon">{icon("info", 16)}</span> Window</h2>
<span class="chip">{shell_kind}</span></div>
<dl class="facts">
<dt>Geometry</dt><dd class="mono">{cfg.state_path()}</dd>
<dt>Backend started</dt><dd class="mono">{_STARTED}</dd>
<dt>Debug keys</dt><dd>{'on — F5, Ctrl+R/F/P and DevTools work' if cfg.debug else 'off — browser keys are suppressed'}</dd>
</dl></section>
<section class="section"><div class="section-head">
<h2 class="section-title"><span class="icon">{icon("shield", 16)}</span> Privacy</h2></div>
<p>All processing is local. There is no delete button anywhere: Charta only moves or copies, and every move can be undone.</p>
<p class="muted">Protected locations (system, Program Files, AppData, drive roots) are refused, never modified.</p></section>"""
    return shell("settings", folder, inner)


# ---- API ----
@app.post("/api/charter")
async def api_charter(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    try:
        assert_not_protected(folder)
    except ProtectedPathError as e:
        # Same non-negotiable guard as the CLI, with a friendly code for the UI.
        return JSONResponse({"error": "protected", "message": str(e)}, status_code=403)
    ch = create_charter_from_text(str(body.get("purpose", "")), _client())
    mode = str(body.get("mode", "")).lower()
    if mode in ("suggest", "auto"):
        ch.mode = mode
    save_charter(pathlib.Path(folder), ch)
    # Start watching right here, on the server that will actually do it. The UI
    # used to fire a second request and ignore its answer, so a failed watch
    # looked like a successful one ("charter ready — watching", nothing watched).
    watching = _start_watching(folder, ch.mode)
    return JSONResponse({"purpose": ch.purpose, "preset": ch.preset,
                         "fields": ch.fields, "mode": ch.mode, "watching": watching})


def _start_watching(folder: str, mode: str = "") -> bool:
    """Put a folder on the watchlist and make sure the daemon is running."""
    try:
        cfg = _cfg()
        watchlist.add(cfg, folder, mode=mode)
        _daemon_get().start()
        _sync_explorer_markers()
        return True
    except Exception as e:  # noqa: BLE001 - the UI reports it, the app keeps going
        applog.get_logger("web").warning("could not start watching %s: %s", folder, e)
        return False


@app.get("/api/file/read")
def api_file_read(folder: str, path: str) -> JSONResponse:
    """Read one file inside a watched folder (text, PDF, DOCX, or a vision summary).

    The path is resolved inside the folder — a traversal outside it is refused.
    """
    bad = _guard(folder)
    if bad:
        return bad
    root = pathlib.Path(folder).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        return JSONResponse({"error": "outside-folder",
                              "message": "Charta only reads files inside the folder."},
                             status_code=400)
    if not target.is_file():
        return JSONResponse({"error": "missing", "message": "That file is not there."},
                             status_code=404)
    if ".charta" in target.parts:
        return JSONResponse({"error": "internal",
                              "message": "That file belongs to Charta."}, status_code=400)
    cfg = _cfg()
    client = LLMClient(cfg)
    result = extract_text(target, _vision(cfg, client))
    return JSONResponse({"file": str(target.relative_to(root)),
                         "text": result.text[:20000],
                         "pages": result.pages, "method": result.method,
                         "size": target.stat().st_size})


@app.get("/api/fs/list")
def api_fs_list(path: str = "") -> JSONResponse:
    """Directory listing for the custom folder picker (folders only)."""
    return JSONResponse(fsbrowse.list_dirs(path or None).as_dict())


def _guard(folder: str) -> JSONResponse | None:
    try:
        assert_not_protected(folder)
    except ProtectedPathError as e:
        return JSONResponse({"error": "protected", "message": str(e)}, status_code=403)
    return None


@app.get("/api/watch/status")
def api_watch_status(folder: str = "") -> JSONResponse:
    """Watched folders (for the tray and the UI) plus tracked count for one folder."""
    cfg = _cfg()
    folders = watchlist.folders(cfg)
    return JSONResponse({
        "watching": bool(folder) and watchlist.is_watched(cfg, folder),
        "folders": folders,
        "active": _daemon.active() if _daemon else [],
        "tracked": len(prop_store.load_proposals(folder)) if folder else 0,
    })


@app.post("/api/watch")
def api_watch(folder: str) -> JSONResponse:
    """Start watching a folder (needs a charter). The daemon scans it on its next tick."""
    bad = _guard(folder)
    if bad:
        return bad
    if load_charter(folder) is None:
        return JSONResponse({"error": "no-charter", "message": "Create a charter first."},
                            status_code=400)
    _start_watching(folder)
    return JSONResponse({"watching": True, "folders": watchlist.folders(_cfg())})


@app.post("/api/unwatch")
def api_unwatch(folder: str) -> JSONResponse:
    cfg = _cfg()
    watchlist.remove(cfg, folder)
    _refresh_thinking()
    _sync_explorer_markers()
    return JSONResponse({"watching": False, "folders": watchlist.folders(cfg)})


@app.post("/api/scan")
def api_scan(folder: str) -> JSONResponse:
    """Scan a folder's existing files now (used by the 'Scan now' button).

    The scan runs in the background so a folder with hundreds of files does not
    freeze the UI; the job id can be polled at ``/api/scan/status``.
    """
    bad = _guard(folder)
    if bad:
        return bad
    cfg = _cfg()
    client = LLMClient(cfg)
    job = str(uuid.uuid4())
    with _scan_lock:
        _scan_jobs[job] = {"folder": folder, "done": 0, "total": 0, "current": "",
                           "state": "starting"}
    thread = threading.Thread(target=_run_scan, args=(job, folder, client), daemon=True)
    thread.start()
    return JSONResponse({"job": job, "scanned": 0, "tracked": len(prop_store.load_proposals(folder))})


def _run_scan(job: str, folder: str, client: LLMClient) -> None:
    """Background scan with progress the page can poll."""
    cfg = _cfg()

    def progress(done: int, total: int, current: str) -> None:
        with _scan_lock:
            _scan_jobs[job].update({"done": done, "total": total, "current": current,
                                     "state": "scanning"})

    try:
        scanned = scan_folder(folder, client, _vision(cfg, client), progress)
        with _scan_lock:
            _scan_jobs[job].update({"done": _scan_jobs[job].get("total", scanned),
                                    "state": "done", "scanned": scanned})
    except Exception as e:  # noqa: BLE001 - report, never crash the server
        with _scan_lock:
            _scan_jobs[job].update({"state": "failed", "error": str(e)})
    watchlist.mark_scanned(cfg, folder)


@app.get("/api/scan/status")
def api_scan_status(job: str = "") -> JSONResponse:
    """Progress of a running scan."""
    with _scan_lock:
        job_state = dict(_scan_jobs.get(job, {}))
    if not job_state:
        return JSONResponse({"error": "unknown-job"}, status_code=404)
    job_state["tracked"] = len(prop_store.load_proposals(job_state.get("folder", "")))
    return JSONResponse(job_state)


OUTPUT_FILES = {"receipts": "receipts.csv", "study": "notes.md",
                "flashcards": "flashcards.csv", "data": "data_entry.csv"}
OUTPUT_KINDS = {
    "receipts": {"title": "Receipts spreadsheet", "ic": "outputs",
                 "desc": "One row per receipt or invoice found here: date, vendor, "
                         "amount and the file it came from. Opens in Excel."},
    "study": {"title": "Study notes", "ic": "notes",
              "desc": "This folder's text distilled into readable notes — headings, "
                      "facts and definitions."},
    "flashcards": {"title": "Flashcards", "ic": "flash",
                   "desc": "Question-and-answer cards built from the notes, for revising."},
    "data": {"title": "Data-entry table", "ic": "table",
             "desc": "One row per file with the charter's fields — the whole folder at a glance."},
}


@app.get("/api/outputs/rows")
def api_output_rows(folder: str, kind: str = "receipts") -> JSONResponse:
    """One output card: what it is, its rows (a short preview), and the files."""
    if kind not in OUTPUT_KINDS:
        return JSONResponse({"error": f"unknown output '{kind}'"}, status_code=400)
    info = OUTPUT_KINDS[kind]
    try:
        if kind == "receipts":
            build_receipts(folder)
        elif kind in ("study", "flashcards"):
            build_study(folder)  # writes the notes and the flashcards together
        else:
            ch = load_charter(folder)
            build_data_entry(folder, list(ch.fields) if ch else [])
    except Exception as e:  # noqa: BLE001 — report, never 500 the UI
        return JSONResponse({"error": str(e)}, status_code=200)
    target = pathlib.Path(folder) / ".charta" / "outputs" / OUTPUT_FILES[kind]
    if not target.exists():
        return JSONResponse({"kind": kind, **info, "columns": [], "rows": [],
                             "total": 0, "file": "", "modified": ""})
    text = target.read_text(encoding="utf-8", errors="replace")
    modified = (datetime.datetime.fromtimestamp(target.stat().st_mtime)
                .strftime("%d %b %Y %H:%M"))
    if target.suffix != ".csv":  # notes: show the Markdown as-is
        return JSONResponse({"kind": kind, **info,
                             "columns": ["note"], "rows": [[text[:6000]]],
                             "total": 1, "file": target.name, "modified": modified})
    import csv as csv_mod

    with target.open(newline="", encoding="utf-8") as fh:
        rows = list(csv_mod.reader(fh))
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    xlsx = target.with_suffix(".xlsx")
    return JSONResponse({"kind": kind, **info,
                         "columns": header, "rows": body[:8],
                         "total": len(body), "file": target.name,
                         "modified": modified,
                         "xlsx": xlsx.name if xlsx.exists() else ""})


@app.post("/api/approve")
async def api_approve(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    props = prop_store.load_proposals(folder)
    files = set(body.get("files", []))
    do_all = bool(body.get("all"))
    done = []
    moves: list[tuple[str, str, str]] = []
    for p in props:
        if p.status == "pending" and (do_all or p.source in files):
            try:
                r = mover_mod.apply_proposal(folder, p)
                p.status = "approved"
                done.append(r.dst)
                moves.append((r.src, r.dst, r.reason))
            except Exception as e:  # noqa: BLE001
                done.append(f"FAILED {p.source}: {e}")
    prop_store.save_proposals(folder, props)
    record.record_moves(_cfg(), folder, moves)
    try:
        build_receipts(folder)
    except Exception:
        pass
    return JSONResponse({"moved": done})


@app.post("/api/reject")
async def api_reject(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    files = set(body.get("files", []))
    props = prop_store.load_proposals(folder)
    for p in props:
        if p.source in files:
            p.status = "rejected"
    prop_store.save_proposals(folder, props)
    return JSONResponse({"ok": True})


@app.post("/api/undo")
def api_undo(folder: str) -> JSONResponse:
    e = journal_mod.undo_last(folder)
    if e:
        record.record_undo(_cfg(), folder, e.get("src", ""), e.get("dst", ""))
    return JSONResponse({"undone": e})


@app.post("/api/outputs")
def api_outputs(folder: str) -> JSONResponse:
    ch = load_charter(folder)
    fields = ch.fields if ch else []
    result = {"receipts": build_receipts(folder),
              "study": build_study(folder),
              "data": build_data_entry(folder, fields)}
    record.record_outputs(_cfg(), folder, ["receipts", "notes", "data table"])
    return JSONResponse(result)


@app.get("/api/chats")
def api_chats(folder: str, limit: int = 20) -> JSONResponse:
    """The folder's saved conversations, newest first."""
    return JSONResponse({"chats": chats.list_chats(folder, limit)})


@app.get("/api/chat")
def api_chat(folder: str, id: str) -> JSONResponse:
    chat = chats.load(folder, id)
    if chat is None:
        return JSONResponse({"error": "no-chat"}, status_code=404)
    return JSONResponse(chat)




@app.post("/api/voice")
async def api_voice(req: Request, provider: str = "",
                    ext: str = "webm") -> JSONResponse:
    """Speech-to-text over HTTP: raw audio bytes in, transcript out.

    The browser records webm/ogg; local providers get a normalised PCM WAV
    copy (see ``charta.voice.stt.as_wav``). The provider/key/model come from
    config.toml — the client never sends secrets.
    """
    from ..voice import stt as stt_mod

    body = await req.body()
    if not body:
        return JSONResponse({"error": "No audio reached the server."},
                            status_code=400)
    if len(body) > 25 * 1024 * 1024:
        return JSONResponse({"error": "That recording is over 25 MB — "
                                      "keep clips under a minute."},
                            status_code=413)
    cfg = _cfg()
    use = provider.strip() or cfg.voice_provider
    try:
        use = stt_mod.normalize(use)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    # One whisper_name per provider; the moonshine field falls back to the
    # whisper field only when it was never set.
    model = cfg.stt_model or cfg.whisper_model if use == stt_mod.MOONSHINE \
        else cfg.whisper_model
    suffix = "." + str(ext or "webm").strip(".")
    tmp = None
    try:
        import tempfile
        tmp = pathlib.Path(tempfile.mktemp(prefix="charta-audio-", suffix=suffix))
        tmp.write_bytes(body)
    except OSError as e:
        return JSONResponse({"error": f"Could not store the recording: {e}"},
                            status_code=500)
    try:
        text = stt_mod.transcribe(tmp, provider=use, model=model,
                                  api_key=cfg.voice_api_key)
        return JSONResponse({"text": text, "provider": use,
                             "cloud": stt_mod.cloud_label(use)})
    except RuntimeError as e:  # friendly, user-facing (missing pkg, key…)
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001 - never leak a stack trace to the UI
        applog.add(cfg, f"voice transcribe failed: {e}")
        return JSONResponse(
            {"error": "Speech-to-text failed unexpectedly. Check "
                      "Settings → Voice for the health of each provider."},
            status_code=500)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


@app.get("/api/settings")
def api_settings_get() -> JSONResponse:
    """The editable settings, read from config.toml (not env secrets)."""
    from ..voice import stt as stt_mod
    path = config_path()
    doc = load_document(path)
    llm = doc.get("llm", {})
    voice = doc.get("voice", {})
    app_cfg = _cfg()
    env_key = (os.environ.get("CHARTA_API_KEY", "").strip()
               or (os.environ.get("OPENAI_API_KEY", "").strip()
                   if app_cfg.llm_provider in ("openai", "openrouter", "groq",
                                               "together", "deepseek") else ""))
    return JSONResponse({
        "config_path": str(path),
        "providers": sorted(PROVIDER_BASE_URLS) + ["custom"],
        "base_urls": PROVIDER_BASE_URLS,
        "llm": {
            "provider": str(llm.get("provider", app_cfg.llm_provider)),
            "base_url": str(llm.get("base_url", "")),
            "api_key_set": bool(str(llm.get("api_key", "")).strip()) or bool(env_key),
            "generation": (str(llm.get("generation", "")
                               or doc.get("models", {}).get("generation", ""))
                           or app_cfg.generation_model),
            "vision_model": str(doc.get("models", {}).get("vision", "")),
            "vision": bool(llm.get("vision", app_cfg.vision)),
            "timeout_seconds": int(doc.get("models", {}).get("timeout_seconds",
                                                             app_cfg.llm_timeout)),
            "retries": int(doc.get("models", {}).get("retries",
                                                     app_cfg.llm_retries)),
        },
        "voice": {
            "provider": str(voice.get("provider", app_cfg.voice_provider)),
            "whisper_model": str(voice.get("whisper_model",
                                           app_cfg.whisper_model)),
            "stt_model": str(voice.get("stt_model", app_cfg.stt_model)),
            "api_key_set": bool(str(voice.get("api_key", "")).strip()),
            "cloud": stt_mod.cloud_label(str(voice.get("provider", "local"))),
            "backends": {p: stt_mod.backend_available(p)
                         for p in stt_mod.PROVIDERS},
        },
    })


@app.post("/api/settings")
async def api_settings_post(req: Request) -> JSONResponse:
    """Save what the Settings UI can edit: [llm], [models] and [voice].

    Secrets: ``"api_key": null`` clears, an empty string keeps the current
    value, a value writes it (into your machine's config.toml, git-ignored).
    """
    body = await req.json()
    path = config_path()
    doc = load_document(path)
    try:
        llm = dict(body.get("llm") or {})
        voice = dict(body.get("voice") or {})
    except AttributeError:
        return JSONResponse({"error": "Send llm/voice objects."},
                            status_code=400)
    models = dict(doc.get("models", {}))

    if llm:
        prov = str(llm.get("provider", "")).strip().lower()
        if prov and prov not in PROVIDER_BASE_URLS and prov != "custom":
            return JSONResponse({"error": f"Unknown AI provider {prov!r}."},
                                status_code=400)
        if prov:
            prev = str(llm.get("provider", doc.get("llm", {}).get("provider", "")))
            cur = str(doc.get("llm", {}).get("provider", prov))
            doc["llm"] = {**(doc.get("llm") or {}), "provider": prov}
            _maybe_reset_base_url(doc, cur, prov)
        if "base_url" in llm:
            url = str(llm.get("base_url") or "").strip()
            if url and not url.startswith(("http://", "https://")):
                return JSONResponse(
                    {"error": "Base URL must start with http:// or https://."},
                    status_code=400)
            doc["llm"]["base_url"] = url
        if "api_key" in llm:
            _apply_secret(doc["llm"], llm.get("api_key"))
        if "generation" in llm and str(llm.get("generation") or "").strip():
            models["generation"] = str(llm["generation"]).strip()
        if "vision_model" in llm:
            models["vision"] = str(llm.get("vision_model") or "").strip()
        if "vision" in llm:
            doc["llm"]["vision"] = bool(llm.get("vision"))
        if "timeout_seconds" in llm:
            models["timeout_seconds"] = _int_or(llm.get("timeout_seconds"), 60, 5, 600)
        if "retries" in llm:
            models["retries"] = _int_or(llm.get("retries"), 1, 0, 5)
        doc["models"] = models

    if voice:
        from ..voice import stt as stt_mod
        vp = str(voice.get("provider", "")).strip().lower()
        if vp:
            try:
                stt_mod.normalize(vp)
            except ValueError:
                return JSONResponse(
                    {"error": f"Unknown speech provider {vp!r}."}, status_code=400)
            doc["voice"] = {**(doc.get("voice") or {}), "provider": vp}
        for field in ("whisper_model", "stt_model"):
            if field in voice:
                doc["voice"][field] = str(voice.get(field) or "").strip()
        if "api_key" in voice:
            _apply_secret(doc["voice"], voice.get("api_key"))

    save_document(doc, path)
    return JSONResponse({"saved": True, "path": str(path)})


def _apply_secret(section: dict, value: object) -> None:
    """null clears the stored key; '' keeps it; a value stores the new one."""
    if value is None:
        section["api_key"] = ""
    elif str(value).strip():
        section["api_key"] = str(value).strip()


def _maybe_reset_base_url(doc: dict, old: str, new: str) -> None:
    """Drop a stock base_url left over from the previous provider."""
    known = {u.rstrip("/") for u in PROVIDER_BASE_URLS.values()}
    cur = str(doc.get("llm", {}).get("base_url", "")).strip().rstrip("/")
    if cur and cur in known and PROVIDER_BASE_URLS.get(old, "").rstrip("/") == cur:
        doc["llm"]["base_url"] = ""


def _int_or(value: object, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


@app.post("/api/ask")
async def api_ask(req: Request, folder: str = "") -> JSONResponse:
    """Start a question. The work is a job the UI can watch step by step."""
    body = await req.json()
    question = str(body.get("q", "")).strip()
    if not folder.strip():
        return JSONResponse({"error": "no-folder",
                             "message": "Pick a folder to ask about first.",
                             "answer": "Pick a folder to ask about first.",
                             "citations": []}, status_code=400)
    if not question:
        return JSONResponse({"error": "no-question", "message": "Type a question.",
                             "answer": "Type a question.", "citations": []}, status_code=400)
    raw_chat = str(body.get("chat") or "").strip()
    if raw_chat == "new":
        chat_id = chats.new_id()      # the Ask page starts a conversation
    elif raw_chat and chats.load(folder, raw_chat) is not None:
        chat_id = raw_chat            # a follow-up in an existing chat
    else:
        chat_id = ""                  # e.g. the dashboard ask box: ephemeral
    job = Job(id=str(uuid.uuid4()), kind="ask")
    job.step("work", f"Reading the index of {_basename(folder)}…")
    if chat_id:
        job.extra["chat"] = chat_id
    with _jobs_lock:
        _jobs[job.id] = job
        if len(_jobs) > 40:
            for old in list(_jobs)[:-40]:
                _jobs.pop(old, None)
    thread = threading.Thread(target=_run_ask, args=(job, folder, question, chat_id),
                              daemon=True)
    thread.start()
    return JSONResponse(job.as_dict())


@app.get("/api/ask/stream")
def api_ask_stream(job: str = "") -> Response:
    """The live story of a question, as it happens (Server-Sent Events).

    Polling shows snapshots; streaming lets the UI draw each step the moment
    it starts — the tool call appears, runs, resolves, and the next one
    begins, exactly like the model is working in front of you.
    """
    import json as json_mod
    import time

    def gen():
        seen = 0
        last_state = None
        deadline = time.time() + 600  # ten minutes is far past any model call
        while time.time() < deadline:
            current = _jobs.get(job)
            if current is None:
                yield f"event: error\ndata: {json_mod.dumps({'error': 'unknown-job'})}\n\n"
                return
            steps = list(current.steps)
            while seen < len(steps):
                s = steps[seen]
                seen += 1
                yield f"event: step\ndata: {json_mod.dumps(s)}\n\n"
            if current.state != last_state and last_state is not None:
                yield (f"event: state\ndata: "
                       f"{json_mod.dumps({'state': current.state, 'error': current.error})}\n\n")
            last_state = current.state
            if current.state in ("done", "failed"):
                yield f"event: done\ndata: {json_mod.dumps(current.as_dict())}\n\n"
                return
            time.sleep(0.15)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/ask/status")
def api_ask_status(job: str = "") -> JSONResponse:
    """The live state of a question: the steps so far and the answer."""
    current = _job(job)
    if current is None:
        return JSONResponse({"error": "unknown-job"}, status_code=404)
    return JSONResponse(current.as_dict())


def _ensure_chat_title(folder: str, chat_id: str, question: str,
                       answer: str, client: object) -> None:
    """The AI names a conversation when its first exchange is recorded.

    The small extra call happens once, before the answer event reaches the
    UI, so the rail already shows the picked title. If the provider is
    unreachable the question's first line becomes the title instead.
    """
    if not chat_id:
        return
    chat = chats.load(folder, chat_id)
    if chat is None or chat.get("title") or len(chat.get("messages") or []) != 1:
        return
    title = chats.ai_title(question, answer, client) or chats.fallback_title(question)
    chats.set_title(folder, chat_id, title)


def _run_ask(job: Job, folder: str, question: str,
              chat_id: str = "") -> None:
    """Do the work, recording every step so the UI can show it."""
    cfg = _cfg()
    client = LLMClient(cfg)
    try:
        idx, cached, stats = _ask_index(folder, cfg, client)
        source = stats.get("source", "index")
        if cached:
            job.step("done", "Used the index (already read).")
        elif source == "index":
            job.step("done", f"Read {len(idx)} chunk(s) from the index.")
        else:
            job.step("done", f"Read {len(idx)} chunk(s) from {stats.get('files', 0)} file(s).")
        if not idx:
            job.state = "done"
            job.answer = ("That folder has nothing indexed yet — scan it first and "
                          "I will have something to read.")
            job.extra.update({"files": 0, "provider": cfg.llm_provider,
                              "model": cfg.generation_model})
            if chat_id:
                chats.append_message(folder, chat_id, question, job.answer)
                _ensure_chat_title(folder, chat_id, question, job.answer, client)
            return
        # The agent: the model gets the index catalogue and the tools, and
        # calls them itself. If it does not use a tool, the plain retrieval
        # path answers instead — the user always gets an answer.
        steps: list[dict] = []
        job.step("work", f"Looking for “{question}”…")
        history = chats.history_for(folder, chat_id)
        if history:
            job.step("work", f"Continuing the conversation ({len(history) // 2} earlier turn(s)).")
        agent = ask_with_tools(question, folder, client, steps=steps, history=history)
        for s in steps:
            job.step(s["kind"], s["text"])
        # The answer arrives in the strict blocks protocol; organisation
        # lines (moves / gaps) are separate — they become Review proposals
        # and AI-gap notes, both awaiting the user.
        if agent.answer:
            cleaned, job.blocks, ai_gaps, new_props = structured_answer(agent.raw or agent.answer)
            job.answer = cleaned
            if new_props:
                for prop in new_props:
                    prop_store.upsert(pathlib.Path(folder), prop)
                job.step("work", f"Proposed {len(new_props)} change(s) — review them before anything moves.")
            if ai_gaps:
                known = load_ai_gaps(folder)
                have = {g.get("note") for g in known}
                for note in ai_gaps:
                    if note not in have:
                        known.append({"note": note,
                                      "at": datetime.datetime.now().isoformat(timespec="seconds")})
                save_ai_gaps(folder, known)
                job.step("work", f"Noticed {len(ai_gaps)} gap(s) in this folder.")
        cited = bool(re.search(r"\[[^\]]+\s+p\d+\]", agent.raw or agent.answer or ""))
        if agent.answer and (agent.used_tools or cited):
            pass  # job.answer already holds the cleaned blocks text
            job.citations = [{"file": c.file, "page": c.page} for c in agent.citations]
            if chat_id:
                chats.append_message(folder, chat_id, question, job.answer,
                                     blocks=job.blocks, model=cfg.generation_model,
                                     citations=job.citations)
                _ensure_chat_title(folder, chat_id, question, job.answer, client)
            job.extra.update({"tools": [c.name for c in agent.calls],
                              "files": len(idx), "provider": cfg.llm_provider,
                              "model": cfg.generation_model, "cached": cached})
            job.state = "done"
            return
        if agent.answer and not agent.used_tools:
            job.step("done", "The model answered from the catalogue — checking it against the files.")
        steps2: list[dict] = []
        ans = answer_query(question, idx, client, steps=steps2)
        for s in steps2:
            job.step(s["kind"], s["text"])
        fallback = ans.text or (
            "I could not find anything about that in this folder. "
            "Try a vendor, a year or an amount from the file name.")
        job.answer, job.blocks, _, _ = structured_answer(fallback)
        job.citations = [{"file": c.file, "page": c.page} for c in ans.citations]
        if chat_id:
            chats.append_message(folder, chat_id, question, job.answer,
                                 blocks=job.blocks, citations=job.citations)
            _ensure_chat_title(folder, chat_id, question, job.answer, client)
        job.state = "done"
        job.extra.update({"files": len(idx), "provider": cfg.llm_provider,
                          "model": cfg.generation_model, "cached": cached})
    except Exception as e:  # noqa: BLE001 — the UI shows the reason
        job.state = "failed"
        job.error = str(e)
        job.step("warn", f"Stopped: {e}")
    finally:
        # Everything the job did goes to the log, so a broken run can be
        # diagnosed from `charta logs` even when the window is the problem.
        asklog = applog.get_logger("ask")
        asklog.info("ask job %s state=%s folder=%s q=%r", job.id, job.state,
                    _basename(folder), question)
        for step in job.steps:
            asklog.info("  [%s] %s", step["kind"], step["text"])
        if job.error:
            asklog.warning("  error: %s", job.error)


# The Ask index per folder, rebuilt only when the folder's files change. The
# first question pays for the reading; every later one is instant.
_ask_cache: dict[str, tuple[str, list[dict], dict]] = {}
_ask_lock = threading.Lock()


def _ai_gaps_path(folder: str | pathlib.Path) -> pathlib.Path:
    return (pathlib.Path(folder) / ".charta" / "ai_gaps.json")


def load_ai_gaps(folder: str | pathlib.Path) -> list[dict]:
    """Gaps the *model* noticed while answering — not an automated scan."""
    p = _ai_gaps_path(folder)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 — a broken file is just no history
        return []


def save_ai_gaps(folder: str | pathlib.Path, gaps: list[dict]) -> None:
    p = _ai_gaps_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(gaps, indent=2), encoding="utf-8")


@dataclass
class Job:
    """A piece of work the UI can watch: what is happening, step by step."""

    id: str
    kind: str = "ask"
    state: str = "running"
    steps: list[dict] = field(default_factory=list)
    answer: str = ""
    blocks: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    error: str = ""
    extra: dict = field(default_factory=dict)

    def step(self, kind: str, text: str) -> None:
        self.steps.append({"kind": kind, "text": text,
                           "at": datetime.datetime.now().strftime("%H:%M:%S")})

    def as_dict(self) -> dict:
        return {"job": self.id, "kind": self.kind, "state": self.state,
                "steps": list(self.steps), "answer": self.answer,
                "blocks": list(self.blocks),
                "citations": list(self.citations), "error": self.error,
                **self.extra}


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _job(job_id: str) -> Job | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _ask_index(folder: str, cfg: AppConfig, client: LLMClient) -> tuple[list[dict], bool, dict]:
    """The index for a folder, from the cache when it is still fresh."""
    key = str(pathlib.Path(folder).resolve())
    signature = index_signature(folder)
    with _ask_lock:
        hit = _ask_cache.get(key)
        if hit and hit[0] == signature:
            return hit[1], True, hit[2]
    stats: dict = {}
    index = build_index(folder, vision=_vision(cfg, client), stats=stats)
    with _ask_lock:
        _ask_cache[key] = (signature, index, stats)
        if len(_ask_cache) > 20:  # keep the cache small
            for old in list(_ask_cache)[:-20]:
                _ask_cache.pop(old, None)
    return index, False, stats


@app.get("/api/version")
def api_version() -> JSONResponse:
    """Which build the server is running (the page compares it with its own)."""
    return JSONResponse({"build": BUILD, "started": _STARTED,
                         "revision": _code_revision(),
                         "version": "0.1.0"})


@app.get("/api/health")
def health() -> JSONResponse:
    """Liveness only — must answer instantly so launchers never time out.

    Provider reachability is deliberately not checked here: a remote or
    slow model ping can take seconds, which made Electron report "no
    response from /api/health" while the server was starting perfectly.
    The Overview banner uses `_provider_up()` for that question instead.
    """
    cfg = _cfg()
    return JSONResponse({"ok": True, "provider": cfg.llm_provider,
                         "base_url": cfg.llm_base_url,
                         "models": [cfg.generation_model]})


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def gen():
        while True:
            yield f"data: {THINKING['msg']}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(gen(), media_type="text/event-stream")
