"""FastAPI local UI: setup, overview, review, outputs, gaps, ask, activity, settings, styleguide."""
from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

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

STATIC = pathlib.Path(__file__).parent / "static"
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


def shell(page: str, folder: str, inner: str, mode: str = "suggest") -> str:
    pill = ('<span class="chip pill-suggest">Suggest mode: nothing moves without you</span>'
            if mode != "auto" else '<span class="chip pill-auto">Auto mode</span>')
    provider = _cfg().llm_provider
    privacy = ("100% local" if provider in ("ollama", "lmstudio", "llamacpp", "vllm")
               else f"cloud: {provider}")
    nav = "".join(
        f'<a href="/{n}?folder={folder}" class="{"active" if page==n else ""}">{icon(n)} {n.title()}</a>'
        for n in ["overview", "review", "outputs", "gaps", "ask", "activity", "settings"])
    return f"""<!doctype html><html data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Charta — {page.title()}</title>
<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/app.css"></head>
<body><div class="layout">
<nav class="sidebar glass" aria-label="Main"><div class="mono">◈ Charta</div>
<div class="chip"><span class="dot dot-idle"></span>{folder or 'no folder'}</div>{nav}
<button onclick="toggleTheme()">◐ Theme</button>
<span class="chip" title="Where the AI runs is set by [llm] in config.toml — local by default.">{privacy}</span></nav>
<div style="flex:1"><div class="topbar"><strong class="mono">{folder}</strong>{pill}
<span class="chip">Ctrl+K</span><span id="thinking" role="status">{THINKING['msg']}</span></div>
<main class="main content">{inner}</main></div></div>
<div id="palette" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);place-items:center" role="dialog" aria-label="Command palette">
<div class="card glass" style="width:480px"><input id="palInput" type="text" placeholder="Type a command…" oninput="palFilter(this.value)" aria-label="Commands">
<div id="palList"><button class="btn btn-ghost" onclick="location.href='/review?folder={folder}'">Approve all</button>
<button class="btn btn-ghost" onclick="undoLast()">Undo last move</button>
<button class="btn btn-ghost" onclick="location.href='/ask?folder={folder}'">Ask</button>
<button class="btn btn-ghost" onclick="closePalette()">Close</button></div></div></div>
<script src="/static/app.js"></script></body></html>"""


def icon(name: str) -> str:
    return {"overview": "◫", "review": "☑", "outputs": "▦", "gaps": "◌",
            "ask": "✎", "activity": "🕘", "settings": "⚙"}.get(name, "•")


@app.get("/", response_class=HTMLResponse)
def setup() -> str:
    chips = "".join(f'<button class="chip" onclick="document.getElementById(\'purpose\').value={p!r}">{n}</button>'
                    for n, p in [("Student", "Lecture PDFs and study screenshots for my CS degree"),
                                 ("Freelancer", "Receipts and invoices I track for freelance taxes"),
                                 ("Data entry", "Data entry: extract name, phone, amount from each form")])
    inner = f"""<div class="card" style="max-width:640px;margin:40px auto">
<div class="chip mono">folder: <span id="fchip">?</span></div>
<h1>What is this folder for?</h1>
<textarea id="purpose" rows="4" placeholder="Lecture PDFs and study screenshots…"></textarea>
<div style="display:flex;gap:12px;align-items:center;margin:12px 0">
<button id="micBtn" class="mic-ring" onclick="toggleMic('purpose')" aria-label="Hold to talk">◉</button>{chips}</div>
<input id="folder" type="text" placeholder="/path/to/folder" aria-label="Folder path">
<button class="btn btn-primary" onclick="create()">Create charter</button>
<div id="out"></div></div>
<script>document.getElementById('fchip').textContent=new URLSearchParams(location.search).get('folder')||'pick below';
async function create(){{const folder=document.getElementById('folder').value||new URLSearchParams(location.search).get('folder')||'.';
const purpose=document.getElementById('purpose').value;
document.getElementById('out').innerHTML='<div class=skeleton>Understanding your purpose… drafting rules… scanning…</div>';
const r=await fetch('/api/charter?folder='+encodeURIComponent(folder),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{purpose}})}});
const j=await r.json();document.getElementById('out').innerHTML='<pre class=mono>'+JSON.stringify(j,null,2)+'</pre><a class=btn href=/overview?folder='+encodeURIComponent(folder)+'>Start watching →</a>';}}
</script>"""
    return shell("overview", "", inner)


@app.get("/styleguide", response_class=HTMLResponse)
def styleguide() -> str:
    inner = """<h1>Styleguide</h1><div class="cards">
<div class="card"><h3>Tokens</h3><div class="chip">chip</div> <span class="chip pill-suggest">suggest</span>
<span class="chip pill-auto">auto</span> <span class="badge-sensitive">sensitive</span></div>
<div class="card"><h3>Buttons</h3><button class="btn btn-primary">Primary</button>
<button class="btn">Default</button><button class="btn btn-ghost">Ghost</button></div>
<div class="card"><h3>Confidence</h3><div class="conf"><span style="width:72%"></span></div>
<div class="skel">skeleton loader</div></div>
<div class="card"><h3>Empty state</h3><p>◌ Nothing here yet.</p><button class="btn">Next action</button></div>
</div>"""
    return shell("overview", "", inner)


def _page(folder: str, name: str) -> tuple[Any, str]:
    ch = load_charter(folder) if folder else None
    return ch, (ch.mode if ch else "suggest")


@app.get("/overview", response_class=HTMLResponse)
def overview(folder: str = "") -> str:
    ch, mode = _page(folder, "overview")
    if folder and ch is None:
        return shell("overview", folder, "<h1>Protected or unknown folder</h1><p>No charter found. Create one from setup.</p>", mode)
    props = prop_store.load_proposals(folder) if folder else []
    pend = [p for p in props if p.status == "pending"]
    gaps = gaps_for_folder(folder, ch.expected) if (folder and ch) else []
    miss = [g for g in gaps if not g.found]
    inner = f"""<div class="cards"><div class="card"><h2>{len(props)}</h2><p>files tracked</p></div>
<div class="card"><h2>{len(pend)}</h2><p>waiting for review</p></div>
<div class="card"><h2>{len(miss)}</h2><p>gaps found</p></div>
<div class="card"><h2>{len(journal_mod.entries(folder)) if folder else 0}</h2><p>moves logged</p></div></div>
<div class="card"><strong>Charta is thinking:</strong> <span id="live">{THINKING['msg']}</span></div>
<div class="cards"><div class="card"><h3>Needs your review</h3><a class="btn" href="/review?folder={folder}">Open review</a></div>
<div class="card"><h3>Missing items</h3><p>{'; '.join(g.note for g in miss[:3]) or 'Nothing missing 🎉'}</p></div>
<div class="card"><h3>Latest outputs</h3><a class="btn" href="/outputs?folder={folder}">View</a></div></div>"""
    return shell("overview", folder, inner, mode)


@app.get("/review", response_class=HTMLResponse)
def review(folder: str = "") -> str:
    _, mode = _page(folder, "review")
    props = prop_store.load_proposals(folder) if folder else []
    if not props:
        return shell("review", folder, '<div class="card"><h2>◌ All clear</h2><p>No proposals. Drop a file in the folder.</p></div>', mode)
    cards = ""
    for p in props:
        if p.status != "pending":
            continue
        sens = '<span class="badge-sensitive">sensitive</span>' if p.sensitive else ""
        cards += f"""<div class="card prop-card fadein"><div class="prop"><span>📄</span><div>
<div class="mono">{p.source} → {p.dest_dir}/{p.new_name}</div>
<div class="conf"><span style="width:{int(p.confidence*100)}%"></span></div>
<p>{p.reason}</p>{sens}<div>
<button class="btn btn-primary" onclick="approveOne({p.source!r})">Approve (A)</button>
<button class="btn" onclick="rejectOne({p.source!r})">Reject (R)</button></div></div></div></div>"""
    tree = "<div class='tree'>📁 " + (folder or ".") + "<br>" + "<br>".join("└─ " + p.dest_dir + "/" + p.new_name for p in props[:8]) + "</div>"
    inner = f"""<p class="mono">J/K move · A approve · R reject · Z undo</p>
<button class="btn btn-primary" onclick="fetch('/api/approve?folder={folder}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{all:true}})}}).then(()=>location.reload())">Approve all high-confidence</button>
{cards}<h3>Before → after preview</h3>{tree}"""
    return shell("review", folder, inner, mode)


@app.get("/outputs", response_class=HTMLResponse)
def outputs(folder: str = "") -> str:
    _, mode = _page(folder, "outputs")
    inner = f"""<div class="card"><h2>Outputs</h2>
<button class="btn" onclick="fetch('/api/outputs?folder={folder}',{{method:'POST'}}).then(r=>r.json()).then(j=>document.getElementById('o').textContent=JSON.stringify(j,null,2))">Rebuild now</button>
<pre id="o" class="mono">click Rebuild</pre></div>"""
    return shell("outputs", folder, inner, mode)


@app.get("/gaps", response_class=HTMLResponse)
def gaps(folder: str = "") -> str:
    ch, mode = _page(folder, "gaps")
    items = gaps_for_folder(folder, ch.expected) if (folder and ch) else []
    done = sum(1 for g in items if g.found)
    pct = int(100 * done / len(items)) if items else 100
    rows = "".join(f"<div class='card'>{'✅' if g.found else '◌ '+g.note}</div>" for g in items) or "<p>◌ No expectations declared.</p>"
    inner = f"<h2>Completeness {pct}%</h2>{rows}"
    return shell("gaps", folder, inner, mode)


@app.get("/ask", response_class=HTMLResponse)
def ask_page(folder: str = "") -> str:
    _, mode = _page(folder, "ask")
    inner = f"""<div class="chatlog" id="log"><div class="msg ai">Ask anything about this folder. I cite file + page, and I won't invent.</div></div>
<div style="display:flex;gap:8px"><input id="q" type="text" placeholder="e.g. What electricity bills do we have for March?">
<button class="btn" onclick="toggleMic('q')">◉</button>
<button class="btn btn-primary" onclick="ask()">Ask</button></div><div id="ans"></div>
<script>async function ask(){{const q=document.getElementById('q').value;
const r=await fetch('/api/ask?folder={folder}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{q}})}});
const j=await r.json();document.getElementById('ans').innerHTML='<div class=card>'+j.answer+'</div>';}}</script>"""
    return shell("ask", folder, inner, mode)


@app.get("/activity", response_class=HTMLResponse)
def activity(folder: str = "") -> str:
    _, mode = _page(folder, "activity")
    rows = "".join(f"<div class='card mono'>{e.get('ts')} — {e.get('src')} → {e.get('dst')} — {e.get('reason')} <button class=btn onclick='undoLast()'>Undo</button></div>"
                   for e in reversed(journal_mod.entries(folder))) if folder else ""
    return shell("activity", folder, rows or "<p>◌ No activity yet.</p>", mode)


@app.get("/settings", response_class=HTMLResponse)
def settings(folder: str = "") -> str:
    cfg = _cfg()
    up = LLMClient(cfg).ping()
    inner = f"""<div class="card"><h2>AI provider</h2><p class="mono">{cfg.llm_provider} · {cfg.llm_base_url}</p>
<p class="mono">gen: {cfg.generation_model} · embed: {cfg.embedding_model} · vision: {'on' if cfg.vision else 'off'}</p>
<p>Status: {'🟢 healthy' if up else '🔴 offline'} <button class="btn" onclick="location.reload()">Check again</button></p>
<p>Change it in <code>config.toml</code> → <code>[llm]</code>: Ollama, LM Studio, OpenAI, OpenRouter, Groq, or any OpenAI-compatible endpoint.</p></div>
<div class="card"><h2>Voice</h2><p>Local Whisper ({cfg.whisper_model}) by default.</p>
<p>ElevenLabs: <span class="badge-sensitive">Cloud: audio leaves your device</span> — off by default.</p></div>
<div class="card"><h2>Privacy</h2><p>All processing is local. There is no delete button anywhere — Charta only moves/copies, and every move can be undone.</p></div>"""
    return shell("settings", folder, inner)


# ---- API ----
@app.post("/api/charter")
async def api_charter(folder: str, req: Request) -> JSONResponse:
    body = await req.json()
    ch = create_charter_from_text(str(body.get("purpose", "")), _client())
    save_charter(pathlib.Path(folder), ch)
    return JSONResponse({"purpose": ch.purpose, "preset": ch.preset, "fields": ch.fields})


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
