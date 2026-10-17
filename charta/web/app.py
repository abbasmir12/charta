"""FastAPI local UI: setup, overview, review, outputs, gaps, ask, activity, settings, styleguide."""
from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import icons
from ..core import applog
from ..core import fsbrowse
from ..core import journal as journal_mod
from ..core import mover as mover_mod
from ..core import proposals as prop_store
from ..core.ask import answer_query, build_index
from ..core.charter import create_charter_from_text, load_charter, save_charter
from ..core.config import AppConfig
from ..core.extract import VisionFn
from ..core.gaps import gaps_for_folder
from ..core.llm import LLMClient
from ..core.outputs import build_data_entry, build_receipts, build_study
from ..core.paths import ProtectedPathError, assert_not_protected

STATIC = pathlib.Path(__file__).parent / "static"
ASSETS = pathlib.Path(__file__).parent.parent / "assets"
ICON = ASSETS / "charta.ico"
app = FastAPI(title="Charta")
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

THINKING: dict[str, str] = {"msg": "Idle — watching nothing yet."}


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


NAV_ITEMS = ["overview", "review", "outputs", "gaps", "ask", "activity", "settings"]
NAV_LABELS = {"overview": "Overview", "review": "Review", "outputs": "Outputs",
              "gaps": "Gaps", "ask": "Ask", "activity": "Activity", "settings": "Settings"}
LOCAL_PROVIDERS = ("ollama", "lmstudio", "llamacpp", "vllm")


def icon(name: str, size: int = 18) -> str:
    """Inline icon by semantic name (see charta/web/icons.py)."""
    return icons.svg(name, size)


def shell(page: str, folder: str, inner: str, mode: str = "suggest") -> str:
    """App shell: title bar + sidebar + content, shared by every screen.

    The same markup is an ordinary header in a browser and the draggable window
    title bar inside Electron (desktop/preload.js sets data-shell).
    """
    pill = ('<span class="chip pill-suggest">Suggest · nothing moves without you</span>'
            if mode != "auto" else '<span class="chip pill-auto">Auto mode</span>')
    provider = _cfg().llm_provider
    if provider in LOCAL_PROVIDERS:
        privacy = ('<span class="chip" title="Where the AI runs is set by [llm] in config.toml.">'
                   f'<span class="icon">{icon("shield", 14)}</span> 100% local</span>')
    else:
        privacy = (f'<span class="chip" title="This folder sends text to {provider}.">'
                   f'<span class="icon">{icon("info", 14)}</span> cloud: {provider}</span>')
    debug = _debug()
    fq = quote(folder)  # folder paths contain spaces, & and backslashes
    nav = "".join(
        f'<a href="/{n}?folder={fq}" class="{"active" if page == n else ""}"'
        f'{" aria-current=\"page\"" if page == n else ""}>'
        f'<span class="icon">{icon(n)}</span> {NAV_LABELS[n]}</a>'
        for n in NAV_ITEMS)
    return f"""<!doctype html><html data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><title>Charta — {page.title() if page else 'Setup'}</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/app.css">
<script>window.__CHARTA_DEBUG__={"true" if debug else "false"};window.__ICONS__={icons.manifest()};</script></head>
<body>
<header class="appbar" id="appbar">
<span class="brand"><span class="mark" aria-hidden="true">{icon("sparkles", 13)}</span> Charta</span>
<span class="path mono" title="{folder}">{folder or 'no folder'}</span>{pill}
<span id="thinking" class="path" role="status" aria-live="polite">{THINKING['msg']}</span>
<span class="spacer"></span>
{privacy}
<span class="kbd" title="Command palette">Ctrl K</span>
</header>
<div class="layout">
<nav class="sidebar" aria-label="Main">
<div class="section caption">Folder</div>
<div class="chip" title="{folder}"><span class="dot dot-idle" aria-hidden="true"></span>{folder or 'none yet'}</div>
<div class="section caption">Workspace</div>{nav}
<div class="foot">
<button type="button" onclick="toggleTheme()"><span class="icon" data-theme-icon>{icon("moon")}</span> <span data-theme-label>Dark theme</span></button>
<a href="/?folder={fq}"><span class="icon">{icon("folder-add")}</span> New charter</a>
</div></nav>
<main class="main content">{inner}</main></div>
<div id="palette" role="dialog" aria-modal="true" aria-label="Command palette">
<div class="card glass"><input id="palInput" type="text" placeholder="Type a command…" oninput="palFilter(this.value)" aria-label="Commands">
<div id="palList" class="stack">
<button type="button" class="btn btn-ghost" onclick="location.href='/review?folder={fq}'"><span class="icon">{icon("check")}</span> Approve all</button>
<button type="button" class="btn btn-ghost" onclick="undoLast()"><span class="icon">{icon("undo")}</span> Undo last move</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/ask?folder={fq}'"><span class="icon">{icon("ask")}</span> Ask the folder</button>
<button type="button" class="btn btn-ghost" onclick="location.href='/outputs?folder={fq}'"><span class="icon">{icon("outputs")}</span> Rebuild outputs</button>
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
def setup(folder: str = "") -> str:
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
<div class="setup-row"><label class="label" for="mode">Mode</label>{mode_dd}
<input id="folder" type="text" class="manual-path" aria-label="Folder path"
 placeholder="or paste a path" value="{initial}"></div>
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
    return shell("", "", inner)


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
                        for n in NAV_ITEMS + ["folder", "file", "undo", "shield", "search", "mic"])
    inner = f"""<h1>Styleguide</h1><div class="cards">
<div class="card"><h3>Colour</h3><div class="row">{swatches}</div></div>
<div class="card"><h3>Icons</h3><div class="row" style="gap:var(--s4);color:var(--text)">{icon_row}</div></div>
<div class="card"><h3>Chips &amp; pills</h3><div class="row"><div class="chip">chip</div>
<span class="chip pill-suggest">suggest</span><span class="chip pill-auto">auto</span>
<span class="badge-sensitive">sensitive</span></div></div>
<div class="card"><h3>Buttons</h3><div class="row"><button class="btn btn-primary"><span class="icon">{icon("sparkles", 16)}</span> Primary</button>
<button class="btn">Default</button><button class="btn btn-ghost">Ghost</button>
<button class="btn btn-icon" aria-label="Icon button">{icon("plus", 16)}</button></div></div>
<div class="card"><h3>Confidence</h3><div class="conf"><span style="width:72%"></span></div>
<div class="skel" style="margin-top:var(--s3)">skeleton loader</div></div>
<div class="card empty" style="padding:var(--s5)"><div class="glyph">{icon("empty", 28)}</div>
<h3>Empty state</h3><p>Nothing here yet.</p><button class="btn">Next action</button></div>
</div>"""
    return shell("", "", inner)


def _page(folder: str, name: str) -> tuple[Any, str]:
    ch = load_charter(folder) if folder else None
    return ch, (ch.mode if ch else "suggest")


def mode_pill(mode: str) -> str:
    return ('<span class="chip pill-auto">Auto mode</span>' if mode == "auto"
            else '<span class="chip pill-suggest">Suggest mode</span>')


def _provider_up() -> bool:
    """Reachability probe for the offline banner (short timeout, never raises)."""
    try:
        return LLMClient(_cfg()).ping(timeout=1.0)
    except Exception:  # noqa: BLE001
        return False


@app.get("/overview", response_class=HTMLResponse)
def overview(folder: str = "") -> str:
    ch, mode = _page(folder, "overview")
    if folder and ch is None:
        return shell("overview", folder, "<h1>Protected or unknown folder</h1><p>No charter found. Create one from setup.</p>", mode)
    props = prop_store.load_proposals(folder) if folder else []
    pend = [p for p in props if p.status == "pending"]
    gaps = gaps_for_folder(folder, ch.expected) if (folder and ch) else []
    miss = [g for g in gaps if not g.found]
    fq = quote(folder)
    purpose = ch.purpose if ch else "no charter yet"
    offline = "" if _provider_up() else (
        f'<div class="banner warn"><span class="icon">{icon("alert", 16)}</span><span>The AI engine is offline, so '
        'classification falls back to built-in rules. Start it, then reload.</span>'
        '<span class="spacer"></span><a class="btn" href="/settings">Settings</a></div>')
    stats = "".join(
        f'<div class="card stat"><div class="n">{value}</div>'
        f'<div class="k"><span class="icon">{icon(ic, 15)}</span>{label}</div></div>'
        for value, label, ic in [
            (len(props), "files tracked", "stack"),
            (len(pend), "waiting for review", "review"),
            (len(miss), "gaps found", "gaps"),
            (len(journal_mod.entries(folder)) if folder else 0, "moves logged", "activity")])
    next_action = (f'<a class="btn btn-primary" href="/review?folder={fq}"><span class="icon">{icon("review", 16)}</span> Review {len(pend)}</a>'
                   if pend else f'<a class="btn" href="/outputs?folder={fq}"><span class="icon">{icon("outputs", 16)}</span> Open outputs</a>')
    inner = f"""{page_head("Overview", purpose, next_action)}
{offline}<div class="cards">{stats}</div>
<div class="card thinking"><span class="pulse" aria-hidden="true"></span>
<span class="icon">{icon("sparkles", 16)}</span>
<span><strong>Charta is thinking:</strong> <span id="live">{THINKING['msg']}</span></span></div>
<div class="cards wide">
<div class="card"><div class="card-head"><h3>Needs your review</h3>{mode_pill(mode)}</div>
<p class="muted">{f'{len(pend)} proposal(s) waiting' if pend else 'Nothing waiting — you are up to date.'}</p>
<a class="btn" href="/review?folder={fq}"><span class="icon">{icon("review", 16)}</span> Open review</a></div>
<div class="card"><div class="card-head"><h3>Missing items</h3></div>
<p class="muted">{'; '.join(g.note for g in miss[:3]) or 'Nothing missing.'}</p>
<a class="btn" href="/gaps?folder={fq}"><span class="icon">{icon("gaps", 16)}</span> Check gaps</a></div>
<div class="card"><div class="card-head"><h3>Latest outputs</h3></div>
<p class="muted">Spreadsheet, notes and tables built from this folder.</p>
<a class="btn" href="/outputs?folder={fq}"><span class="icon">{icon("outputs", 16)}</span> View outputs</a></div></div>"""
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
        cards += f"""<div class="card prop-card fadein"><div class="prop">
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
    inner = f"""{page_head("Review", f"{len(pending)} proposal(s) — nothing moves without you.",
        f'<button class="btn" onclick="undoLast()"><span class="icon">{icon("undo", 16)}</span> Undo last move</button>'
        f'<button class="btn btn-primary" onclick="{approve_all}"><span class="icon">{icon("check", 16)}</span> Approve all</button>')}
<div class="legend"><span><span class="kbd">J</span>/<span class="kbd">K</span> move</span>
<span><span class="kbd">A</span> approve</span><span><span class="kbd">R</span> reject</span>
<span><span class="kbd">Esc</span> close</span></div>
<div class="stack">{cards}</div>
<h3 class="section-title">Before → after preview</h3>{tree}"""
    return shell("review", folder, inner, mode)


@app.get("/outputs", response_class=HTMLResponse)
def outputs(folder: str = "") -> str:
    ch, mode = _page(folder, "outputs")
    fq = quote(folder)
    tabs = "".join(
        f'<button type="button" role="tab" aria-selected="{str(i == 0).lower()}" '
        f'onclick="loadOutput(this,{kind!r})">{label}</button>'
        for i, (kind, label) in enumerate([("receipts", "Spreadsheet"), ("study", "Notes"),
                                           ("flashcards", "Flashcards"), ("data", "Table")]))
    rebuild = (f"fetch('/api/outputs?folder={fq}',{{method:'POST'}}).then(r=>r.json())"
               ".then(j=>{document.getElementById('o').textContent=JSON.stringify(j,null,2);loadOutput()})")
    inner = f"""{page_head("Outputs", (ch.purpose if ch else "Build a spreadsheet, notes and tables from this folder."),
        f'<button class="btn" onclick="{rebuild}"><span class="icon">{icon("scan", 16)}</span> Rebuild now</button>')}
<div class="card"><div class="tabbar" role="tablist" aria-label="Output type">{tabs}</div>
<div id="outGrid"><div class="skel" style="height:88px">loading outputs…</div></div>
<details style="margin-top:var(--s4)"><summary class="muted">Rebuild details</summary>
<pre id="o" class="mono" style="white-space:pre-wrap">—</pre></details></div>"""
    return shell("outputs", folder, inner, mode)


@app.get("/gaps", response_class=HTMLResponse)
def gaps(folder: str = "") -> str:
    ch, mode = _page(folder, "gaps")
    items = gaps_for_folder(folder, ch.expected) if (folder and ch) else []
    done = sum(1 for g in items if g.found)
    pct = int(100 * done / len(items)) if items else 100
    fq = quote(folder)
    rows = "".join(
        f'<div class="card gap {"found" if g.found else "missing"}">'
        f'<span class="icon">{icon("check", 16) if g.found else icon("empty", 16)}</span>'
        f'<span>{g.note}</span></div>' for g in items)
    if not rows:
        body = empty_state("gaps", "No expectations declared",
                           "Add an \"Expected items\" list to the charter and Charta will tell you what is missing.",
                           f'<a class="btn" href="/?folder={fq}"><span class="icon">{icon("folder-add", 16)}</span> Edit charter</a>')
    else:
        body = f'<div class="stack">{rows}</div>'
    ring = (f'<div class="ring" style="--pct:{pct}" role="img" '
            f'aria-label="completeness {pct} percent"><span>{pct}%</span></div>')
    inner = f"""{page_head("Gaps", f"{done} of {len(items)} expected items present.", ring)}
{body}"""
    return shell("gaps", folder, inner, mode)


@app.get("/ask", response_class=HTMLResponse)
def ask_page(folder: str = "") -> str:
    ch, mode = _page(folder, "ask")
    fq = quote(folder)
    starters = "".join(
        f'<button type="button" class="chip" onclick="askFolder({q!r})">{q}</button>'
        for q in (["What is in this folder?", "Summarise the newest files"]
                  + ([f"What about {ch.expected[0]}?"] if ch and ch.expected else [])))
    inner = f"""{page_head("Ask", "Answers cite file and page. If it is not in the folder, Charta says so.")}
<div class="chatlog" id="log" role="log" aria-live="polite">
<div class="msg ai">Ask anything about this folder — I quote the file and page I used, and I won't invent an answer.</div></div>
<div class="row"><input id="q" type="text" aria-label="Your question" placeholder="e.g. What electricity bills do we have for March?">
<button type="button" class="btn btn-icon" onclick="toggleMic('q')" aria-label="Ask by voice">{icon("mic", 18)}</button>
<button type="button" class="btn btn-primary" onclick="askFolder()"><span class="icon">{icon("arrow-right", 16)}</span> Ask</button></div>
<div class="row" style="margin-top:var(--s3)">{starters}</div>
<div id="ans"></div>"""
    return shell("ask", folder, inner, mode)


@app.get("/activity", response_class=HTMLResponse)
def activity(folder: str = "") -> str:
    _, mode = _page(folder, "activity")
    entries = list(reversed(journal_mod.entries(folder))) if folder else []
    rows = "".join(
        f'<div class="card"><div class="row"><span class="chip mono">{e.get("ts", "")}</span>'
        f'<span class="spacer"></span><button class="btn btn-ghost" onclick="undoLast()"><span class="icon">{icon("undo", 16)}</span> Undo</button></div>'
        f'<p class="mono">{e.get("src", "")} → {e.get("dst", "")}</p>'
        f'<p class="muted">{e.get("reason", "")}</p></div>'
        for e in entries)
    if not rows:
        rows = empty_state("history", "No activity yet",
                           "Every move lands here with the reason it was made, and each one can be undone.")
    inner = f"""{page_head("Activity", "Every change Charta made, newest first.")}
<div class="stack">{rows}</div>"""
    return shell("activity", folder, inner, mode)


@app.get("/settings", response_class=HTMLResponse)
def settings(folder: str = "", req: Request = None) -> str:  # type: ignore[assignment]
    cfg = _cfg()
    up = LLMClient(cfg).ping()
    # The backend cannot otherwise know which shell is hosting the UI.
    user_agent = (req.headers.get("user-agent", "") if req else "")
    shell_kind = "Electron desktop" if "Electron" in user_agent else "browser"
    inner = f"""{page_head("Settings", "Everything here lives in config.toml on your machine.")}
<div class="cards wide">
<div class="card"><div class="card-head"><h3><span class="icon">{icon("sparkles", 16)}</span> AI provider</h3>
<span class="chip {'pill-suggest' if up else 'pill-auto'}">{'healthy' if up else 'offline'}</span></div>
<p class="mono">{cfg.llm_provider} · {cfg.llm_base_url}</p>
<p class="muted mono">gen {cfg.generation_model} · embed {cfg.embedding_model} · vision {'on' if cfg.vision else 'off'}</p>
<div class="row"><button class="btn" onclick="location.reload()"><span class="icon">{icon("undo", 16)}</span> Check again</button></div>
<p class="muted">`charta doctor` prints the full report; the log is at <code>{applog.log_path(cfg)}</code>.</p>
<p class="muted">Any OpenAI-compatible endpoint works: edit <code>[llm]</code> in <code>config.toml</code>.</p></div>
<div class="card"><div class="card-head"><h3><span class="icon">{icon("info", 16)}</span> Window</h3><span class="chip">{shell_kind}</span></div>
<p class="muted">Geometry is remembered in <code>{cfg.state_path()}</code>.</p>
<p class="muted mono">debug: {'on — F5/Ctrl+R/F/P and DevTools work' if cfg.debug else 'off — browser keys are suppressed'}</p></div>
<div class="card"><div class="card-head"><h3><span class="icon">{icon("mic", 16)}</span> Voice</h3></div>
<p class="muted">Local Whisper ({cfg.whisper_model}) by default.</p>
<p>ElevenLabs <span class="badge-sensitive">cloud: audio leaves your device</span> — off by default.</p></div>
<div class="card"><div class="card-head"><h3><span class="icon">{icon("shield", 16)}</span> Privacy</h3></div>
<p>All processing is local. There is no delete button anywhere — Charta only moves or copies, and every move can be undone.</p>
<p class="muted">Protected locations (system, Program Files, AppData, drive roots) are refused, never modified.</p></div></div>"""
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
    return JSONResponse({"purpose": ch.purpose, "preset": ch.preset,
                         "fields": ch.fields, "mode": ch.mode})


@app.get("/api/fs/list")
def api_fs_list(path: str = "") -> JSONResponse:
    """Directory listing for the custom folder picker (folders only)."""
    return JSONResponse(fsbrowse.list_dirs(path or None).as_dict())


OUTPUT_FILES = {"receipts": "receipts.csv", "study": "notes.md",
                "flashcards": "flashcards.csv", "data": "data_entry.csv"}


@app.get("/api/outputs/rows")
def api_output_rows(folder: str, kind: str = "receipts") -> JSONResponse:
    """Rows for the output grid (rebuilt on demand, then parsed server-side)."""
    if kind not in OUTPUT_FILES:
        return JSONResponse({"error": f"unknown output '{kind}'"}, status_code=400)
    try:
        if kind == "receipts":
            build_receipts(folder)
        elif kind == "study":
            build_study(folder)
        else:
            ch = load_charter(folder)
            build_data_entry(folder, list(ch.fields) if ch else [])
    except Exception as e:  # noqa: BLE001 — report, never 500 the UI
        return JSONResponse({"error": str(e)}, status_code=200)
    target = pathlib.Path(folder) / ".charta" / "outputs" / OUTPUT_FILES[kind]
    if not target.exists():
        return JSONResponse({"columns": [], "rows": [], "path": str(target)})
    text = target.read_text(encoding="utf-8", errors="replace")
    if target.suffix != ".csv":  # notes: show the Markdown as-is
        return JSONResponse({"columns": ["markdown"], "rows": [[text[:6000]]], "path": str(target)})
    import csv as csv_mod

    with target.open(newline="", encoding="utf-8") as fh:
        rows = list(csv_mod.reader(fh))
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    return JSONResponse({"columns": header, "rows": body[:500], "path": str(target)})


@app.post("/api/approve")
async def api_approve(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    props = prop_store.load_proposals(folder)
    files = set(body.get("files", []))
    do_all = bool(body.get("all"))
    done = []
    for p in props:
        if p.status == "pending" and (do_all or p.source in files):
            try:
                r = mover_mod.apply_proposal(folder, p)
                p.status = "approved"
                done.append(r.dst)
            except Exception as e:  # noqa: BLE001
                done.append(f"FAILED {p.source}: {e}")
    prop_store.save_proposals(folder, props)
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
    return JSONResponse({"undone": e})


@app.post("/api/outputs")
def api_outputs(folder: str) -> JSONResponse:
    ch = load_charter(folder)
    fields = ch.fields if ch else []
    return JSONResponse({"receipts": build_receipts(folder),
                         "study": build_study(folder),
                         "data": build_data_entry(folder, fields)})


@app.post("/api/ask")
async def api_ask(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    cfg = _cfg()
    client = LLMClient(cfg)
    idx = build_index(folder, client, vision=_vision(cfg, client))
    ans = answer_query(str(body.get("q", "")), idx, client)
    return JSONResponse({"answer": ans.text,
                         "citations": [{"file": c.file, "page": c.page} for c in ans.citations]})


@app.get("/api/health")
def health() -> JSONResponse:
    cfg = _cfg()
    return JSONResponse({"provider": cfg.llm_provider, "base_url": cfg.llm_base_url,
                         "llm": LLMClient(cfg).ping(), "models": [cfg.generation_model]})


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def gen():
        while True:
            yield f"data: {THINKING['msg']}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(gen(), media_type="text/event-stream")
