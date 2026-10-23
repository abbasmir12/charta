"""Web UI polish: debug flag, icon, protected refusal, folder picker, charter mode."""
from __future__ import annotations

import json

import pathlib
import re
import pytest
from fastapi.testclient import TestClient

from charta.core.charter import load_charter
from charta.web.app import app


@pytest.fixture
def client(monkeypatch):
    # Point the provider at a closed port: AI calls fail fast and fall back.
    # The state dir (watched-folder registry) is set by the autouse fixture.
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:9/v1")
    return TestClient(app)

def _wait_job(client, job: str, timeout: float = 30.0) -> dict:
    """Wait for a background job (the UI polls the same way)."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get("/api/ask/status", params={"job": job}).json()
        if state.get("state") in ("done", "failed"):
            return state
        time.sleep(0.05)
    raise AssertionError("the job did not finish in time")


def _wait_scan(client, job: str, timeout: float = 20.0) -> dict:
    """Wait for a background scan to finish (the UI polls the same way)."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get("/api/scan/status", params={"job": job}).json()
        if state.get("state") in ("done", "failed"):
            return state
        time.sleep(0.05)
    raise AssertionError("the scan did not finish in time")


def test_health_never_waits_on_the_provider(client, monkeypatch):
    """The launcher probes /api/health with a 1.5s timeout; a model ping there
    used to make a healthy server look dead."""
    from charta.core.llm import LLMClient

    def boom(*_a, **_k):
        raise AssertionError("/api/health must not call the model")

    monkeypatch.setattr(LLMClient, "ping", boom)
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["provider"] and "llm" not in body


def test_debug_flag_defaults_off_and_follows_env(client, monkeypatch):
    monkeypatch.delenv("CHARTA_DEBUG", raising=False)
    assert "window.__CHARTA_DEBUG__=false" in client.get("/").text
    monkeypatch.setenv("CHARTA_DEBUG", "1")
    assert "window.__CHARTA_DEBUG__=true" in client.get("/").text


def test_favicon_is_the_multi_size_ico(client):
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert res.content[:6] == b"\x00\x00\x01\x00\x07\x00"


def test_protected_refusal_page_is_friendly(client):
    res = client.get("/protected?folder=C:\\Windows")
    assert res.status_code == 200
    assert "won't watch this folder" in res.text
    assert "Nothing here was read, moved or changed" in res.text


def test_folder_picker_api_lists_only_folders(client, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "a.txt").write_text("x")
    body = client.get("/api/fs/list", params={"path": str(tmp_path)}).json()
    assert body["dirs"] == ["docs"] and body["protected"] is False
    assert body["path"] and body["roots"]


def test_charter_is_refused_for_protected_folders(client):
    res = client.post("/api/charter", params={"folder": "C:\\Windows"}, json={"purpose": "sneaky"})
    assert res.status_code == 403
    assert res.json()["error"] == "protected"
    assert "protected" in res.json()["message"].lower()


def test_charter_persists_the_chosen_mode(client, tmp_path):
    res = client.post("/api/charter", params={"folder": str(tmp_path)},
                      json={"purpose": "receipts and invoices", "mode": "auto"})
    assert res.status_code == 200 and res.json()["mode"] == "auto"
    charter = load_charter(tmp_path)
    assert charter is not None and charter.mode == "auto"


def test_setup_screen_has_picker_and_custom_dropdown(client):
    html = client.get("/").text
    assert 'id="fsPicker"' in html and "openPicker()" in html
    assert 'class="dd"' in html and "<select" not in html


def test_watch_requires_a_charter(client, tmp_path):
    res = client.post("/api/watch", params={"folder": str(tmp_path)})
    assert res.status_code == 400
    assert res.json()["error"] == "no-charter"


def test_watch_unwatch_and_status_round_trip(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    res = client.post("/api/watch", params={"folder": str(tmp_path)})
    assert res.status_code == 200 and res.json()["watching"] is True

    status = client.get("/api/watch/status", params={"folder": str(tmp_path)}).json()
    assert status["watching"] is True
    assert str(tmp_path.resolve()) in status["folders"]

    res = client.post("/api/unwatch", params={"folder": str(tmp_path)})
    assert res.json()["watching"] is False
    assert str(tmp_path.resolve()) not in client.get(
        "/api/watch/status").json()["folders"]


def test_scan_endpoint_proposes_existing_files(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    body = client.post("/api/scan", params={"folder": str(tmp_path)}).json()
    assert body["job"]
    done = _wait_scan(client, body["job"])
    assert done["state"] == "done" and done["scanned"] == 1
    assert done["tracked"] == 1


def test_watch_is_refused_for_protected_folders(client):
    res = client.post("/api/watch", params={"folder": "C:\\Windows"})
    assert res.status_code == 403 and res.json()["error"] == "protected"


def test_setup_redirects_to_overview_when_a_charter_exists(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    res = client.get("/", params={"folder": str(tmp_path)}, follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"].startswith("/overview")


def test_setup_redirects_protected_folder_to_the_refusal_screen(client):
    res = client.get("/", params={"folder": "C:\\Windows"}, follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "/protected" in res.headers["location"]



def test_folders_page_lists_the_watched_folders(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    client.post("/api/watch", params={"folder": str(tmp_path)})
    text = client.get("/folders").text
    assert "Watched folders" in text
    assert tmp_path.name in text
    assert "1 folder watched" in text
    assert "Ask about this folder" in text or "Ask about" in text


def test_unwatching_keeps_the_folder_and_its_analysis(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    client.post("/api/watch", params={"folder": str(tmp_path)})
    job = client.post("/api/scan", params={"folder": str(tmp_path)}).json()["job"]
    _wait_scan(client, job)
    client.post("/api/unwatch", params={"folder": str(tmp_path)})

    text = client.get("/folders").text
    assert "Paused" in text and "Resume watching" in text
    assert "0 folders watched" in text
    # The analysis is still there: the file keeps its index state.
    files = client.get("/files", params={"folder": str(tmp_path)}).text
    assert "lecture_07.txt" in files and "pending" in files


def test_files_page_lists_files_and_reads_them(client, tmp_path):
    (tmp_path / "notes.md").write_text("hello from the folder", encoding="utf-8")
    text = client.get("/files", params={"folder": str(tmp_path)}).text
    assert "notes.md" in text and "Read" in text
    body = client.get("/api/file/read", params={"folder": str(tmp_path),
                                                 "path": "notes.md"}).json()
    assert body["text"] == "hello from the folder"
    assert body["method"] == "text"


def test_file_read_refuses_paths_outside_the_folder(client, tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    res = client.get("/api/file/read", params={"folder": str(tmp_path),
                                                "path": "../secret.txt"})
    assert res.status_code == 400
    assert res.json()["error"] == "outside-folder"


def test_history_page_lists_the_commits_charta_made(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    client.post("/api/watch", params={"folder": str(tmp_path)})
    job = client.post("/api/scan", params={"folder": str(tmp_path)}).json()["job"]
    _wait_scan(client, job)
    text = client.get("/history", params={"folder": str(tmp_path)}).text
    assert "charta: indexed" in text
    assert "lecture_07.txt" in text


def test_folders_page_shows_the_history_count(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    client.post("/api/watch", params={"folder": str(tmp_path)})
    job = client.post("/api/scan", params={"folder": str(tmp_path)}).json()["job"]
    _wait_scan(client, job)
    text = client.get("/folders").text
    assert "commits</a>" in text


def test_editing_a_file_keeps_the_old_version(client, tmp_path):
    (tmp_path / "notes.md").write_text("first", encoding="utf-8")
    res = client.post("/api/file/write", params={"folder": str(tmp_path)},
                      json={"path": "notes.md", "text": "second"})
    assert res.status_code == 200
    assert res.json()["backup"] == "notes.md.charta-old"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "second"
    assert (tmp_path / "notes.md.charta-old").read_text(encoding="utf-8") == "first"


def test_trashing_a_file_moves_it_and_it_can_come_back(client, tmp_path):
    (tmp_path / "old.txt").write_text("keep", encoding="utf-8")
    res = client.post("/api/file/trash", params={"folder": str(tmp_path)},
                      json={"path": "old.txt"})
    assert res.status_code == 200
    assert not (tmp_path / "old.txt").exists()
    listed = client.get("/api/file/trash", params={"folder": str(tmp_path)}).json()["items"]
    assert listed and listed[0]["was"] == "old.txt"
    back = client.post("/api/file/restore", params={"folder": str(tmp_path)},
                       json={"path": listed[0]["path"]})
    assert back.status_code == 200
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "keep"


def test_file_tools_refuse_to_write_outside_the_folder(client, tmp_path):
    res = client.post("/api/file/write", params={"folder": str(tmp_path)},
                      json={"path": "../escaped.md", "text": "nope"})
    assert res.status_code == 400
    assert res.json()["error"] == "tool-error"



def test_a_folder_can_switch_between_suggest_and_auto_mode(client, tmp_path):
    from charta.core.charter import load_charter, preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    assert load_charter(tmp_path).mode == "suggest"
    res = client.post("/api/mode", params={"folder": str(tmp_path), "mode": "auto"})
    assert res.status_code == 200 and res.json()["mode"] == "auto"
    assert load_charter(tmp_path).mode == "auto"
    back = client.post("/api/mode", params={"folder": str(tmp_path), "mode": "suggest"})
    assert back.status_code == 200
    assert load_charter(tmp_path).mode == "suggest"


def test_the_mode_switch_rejects_nonsense_and_protected_folders(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    res = client.post("/api/mode", params={"folder": str(tmp_path), "mode": "yolo"})
    assert res.status_code == 400
    protected = client.post("/api/mode", params={"folder": "C:\\Windows", "mode": "auto"})
    assert protected.status_code == 403


def test_creating_a_charter_starts_watching_right_away(client, tmp_path):
    """The setup screen used to fire a second request and ignore its answer,
    so a failed watch looked like a successful one."""
    res = client.post("/api/charter", params={"folder": str(tmp_path)},
                      json={"purpose": "Lecture PDFs for my degree", "mode": "suggest"})
    assert res.status_code == 200
    body = res.json()
    assert body["watching"] is True
    assert str(tmp_path.resolve()) in client.get("/api/watch/status").json()["folders"]


def test_an_empty_watched_folder_says_so_instead_of_scanning(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    client.post("/api/watch", params={"folder": str(tmp_path)})
    text = client.get("/overview", params={"folder": str(tmp_path)}).text
    assert "This folder is empty" in text
    assert "watching it" in text


def test_asking_without_a_folder_says_so_instead_of_guessing(client):
    """An empty folder used to mean 'the current directory' — the whole repo."""
    res = client.post("/api/ask", params={"folder": ""}, json={"q": "what is in here?"})
    assert res.status_code == 400
    assert res.json()["error"] == "no-folder"
    page = client.get("/ask").text
    assert "Which folder?" in page


def test_asking_uses_the_configured_provider_and_model(client, tmp_path, monkeypatch):
    (tmp_path / "note.txt").write_text("The sponsorship for 2026 is 5000 EUR.", encoding="utf-8")
    monkeypatch.setenv("CHARTA_MODEL", "fake-model")
    started = client.post("/api/ask", params={"folder": str(tmp_path)},
                          json={"q": "what is the 2026 sponsorship?"}).json()
    body = _wait_job(client, started["job"])
    assert body["files"] == 1
    assert body["model"] == "fake-model"
    assert body["provider"]
    assert body["steps"]  # the work is visible while it happens
    assert "sponsorship" in body["answer"].lower() or body["citations"]


def test_ask_reads_the_folder_once_and_then_answers_from_the_cache(client, tmp_path):
    (tmp_path / "sponsorship_2026.txt").write_text(
        "Sponsorship agreement 2026 with Acme Corp. Amount: 5000 EUR.", encoding="utf-8")
    first = _wait_job(client, client.post("/api/ask", params={"folder": str(tmp_path)},
                                         json={"q": "what is the 2026 sponsorship?"}).json()["job"])
    assert first["files"] == 1
    second = _wait_job(client, client.post("/api/ask", params={"folder": str(tmp_path)},
                                          json={"q": "and the amount?"}).json()["job"])
    assert second["cached"] is True and second["files"] == 1
    assert second["citations"]


def test_ask_reports_how_much_of_the_folder_it_read(client, tmp_path):
    for i in range(5):
        (tmp_path / f"file{i}.txt").write_text(f"note {i}", encoding="utf-8")
    body = _wait_job(client, client.post("/api/ask", params={"folder": str(tmp_path)},
                                        json={"q": "what are the notes?"}).json()["job"])
    assert body["files"] == 5
    assert body["state"] == "done"


def test_a_question_always_produces_an_answer(client, tmp_path):
    """Even a model that misbehaves must not leave the user with nothing."""
    (tmp_path / "note.txt").write_text("The sponsorship for 2026 is 5000 EUR.", encoding="utf-8")
    job = client.post("/api/ask", params={"folder": str(tmp_path)},
                      json={"q": "tell me about the sponsorship"}).json()
    body = _wait_job(client, job["job"])
    assert body["state"] == "done"
    assert body["answer"].strip()


def test_the_page_carries_a_build_stamp_and_the_server_reports_its_own(client):
    """A window left open across an update must notice and offer a reload."""
    page = client.get("/ask", params={"folder": ""}).text
    assert "__CHARTA_BUILD__" in page
    version = client.get("/api/version").json()
    assert version["build"] and version["started"]
    assert version["build"] in page


def test_every_ask_box_polls_the_job():
    """/api/ask is a job; any box that reads j.answer from it directly shows
    "No answer." instantly and never asks the model — the bug that looked
    like a broken model. Guard every ask *function* against it."""
    src = (pathlib.Path(__file__).parent.parent / "charta" / "web"
           / "static" / "app.js").read_text(encoding="utf-8")
    asking = ["askFolder", "askIn"]
    starts = {name: src.index(f"window.{name}=") for name in asking}
    ends = {name: src.find("\n};", starts[name]) for name in asking}
    assert all(end > start for start, end in zip(starts.values(), ends.values()))
    for name in asking:
        body = src[starts[name]:ends[name]]
        assert "/api/ask?" in body, f"{name} must ask /api/ask"
        assert "askOnce(" in body, f"{name} must go through the shared job flow"
        assert re.search(r"j\.answer", body) is None, (
            f"{name} must read done.answer from the streamed job, not j.answer")
    # the shared flow itself streams the job and renders the polled answer
    shared = src[src.index("async function askOnce"):src.index("window.askFolder")]
    assert "streamJob(" in shared and "watchJob(" in shared
    # And no function anywhere may fall back to the old literal.
    assert src.count("No answer.") == 0


def test_pages_and_scripts_come_with_no_store(client):
    """A cached app.js against a changed API looks like a broken feature.
    The server must never let the browser reuse them."""
    assert client.get("/").headers.get("cache-control") == "no-store"
    assert client.get("/static/app.js").headers.get("cache-control") == "no-store"


def test_the_ask_stream_sends_steps_then_a_final_done(client, tmp_path):
    """SSE: steps arrive as events, and a last "done" event has the answer."""
    (tmp_path / "a.txt").write_text("The sponsorship is 5000 EUR.", encoding="utf-8")
    job = client.post("/api/ask", params={"folder": str(tmp_path)},
                      json={"q": "what is the sponsorship?"}).json()
    assert job.get("job")
    events: list[tuple[str, str]] = []
    with client.stream("GET", "/api/ask/stream",
                       params={"job": job["job"]}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event: "):
                events.append((line[7:], ""))
            elif line.startswith("data: ") and events:
                events[-1] = (events[-1][0], line[6:])
                if events[-1][0] == "done":
                    break
    kinds = [json.loads(d)["kind"] for e, d in events if e == "step" and d]
    assert "work" in kinds
    assert events[-1][0] == "done"
    final = json.loads(events[-1][1])
    assert final["state"] == "done"
    assert final["answer"]


def test_a_model_gap_lands_in_the_ai_gaps(client, tmp_path, monkeypatch):
    """GAP: lines the model writes become AI-gap notes for the gaps page."""
    from charta.core.agent import AgentResult
    import charta.web.app as web_app

    def fake(question, folder, llm_client, steps=None, rounds=5):
        if steps is not None:
            steps.append({"kind": "done", "text": "Answer ready."})
        return AgentResult(
            answer="The March bill is not here.\n\nGAP: no electricity bill for March",
            citations=[], calls=[], used_tools=True, files=["b.txt"])

    monkeypatch.setattr(web_app, "ask_with_tools", fake)
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    body = client.post("/api/ask", params={"folder": str(tmp_path)},
                       json={"q": "what?"}).json()
    _wait_job(client, body["job"])
    gaps = web_app.load_ai_gaps(tmp_path)
    assert gaps and gaps[0]["note"] == "no electricity bill for March"


def test_the_ask_page_has_one_ask_function_per_name():
    """A duplicate askFolder overwrote the streaming one and broke the flow
    with 'work.add is not a function'. The wiring must stay unique."""
    src = (pathlib.Path(__file__).parent.parent / "charta" / "web"
           / "static" / "app.js").read_text(encoding="utf-8")
    for name in ("window.askFolder=", "window.askIn=", "async function askOnce",
                 "function makeWork", "function streamJob", "async function watchJob"):
        assert src.count(name) == 1, f"{name} must be defined exactly once"
    # The ask entry points must go through askOnce (the streamed flow).
    ask = src[src.index("window.askFolder="):src.index("// --- keep the page in step")]
    assert "askOnce(" in ask and "watchJob(j.job,(done)" not in ask
    ask_in = src[src.index("window.askIn="):src.index("window.openFile=")]
    assert "askOnce(" in ask_in


def test_markdown_headings_render_as_real_headlines():
    """'### Title' must become a visible headline, never literal hashes.
    The regex must allow a missing space after the hashes, and every heading
    level must have its own CSS (h5 used to be unstyled, so ### looked like
    plain small text even when it parsed)."""
    src = (pathlib.Path(__file__).parent.parent / "charta" / "web" / "static"
           / "app.js").read_text(encoding="utf-8")
    assert re.search(r"\(\\?#\{1,6\}\)\\s\*\(", src), "heading regex lost its no-space tolerance"
    css = (pathlib.Path(__file__).parent.parent / "charta" / "web" / "static"
           / "app.css").read_text(encoding="utf-8")
    for tag in ("h3", "h4", "h5"):
        assert f".msg.rich {tag}{{" in css, f"{tag} has no headline style"
    # If node exists, execute md() end to end — the strongest check.
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return  # source assertions above still guard the regression
    script = """
const fs=require('fs');
const src=fs.readFileSync(process.argv[1],'utf8');
const grab=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b));
const escHtml=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
eval(grab('function mdInline(','window.revealCite'));
const out=md(['## Summary','###NoSpace','####Deep','**Bold heading**'].join('\\n'));
if(!/<h3>Summary<\\/h3>/.test(out))throw new Error('## broken');
if(!/<h4>NoSpace<\\/h4>/.test(out))throw new Error('### without space still literal');
if(!/<h5>Deep<\\/h5>/.test(out))throw new Error('#### broken');
if(/#{2,6}/.test(out))throw new Error('hashes leak into the answer');
console.log('ok');
"""
    js = pathlib.Path(__file__).parent.parent / "charta" / "web" / "static" / "app.js"
    r = subprocess.run([node, "-e", script, str(js)], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, f"md() failed: {r.stderr}"


def test_the_blocks_protocol_reaches_the_browser(client, tmp_path, monkeypatch):
    """A model answering in the strict JSON protocol produces validated
    blocks on the job payload the SSE stream and UI consume."""
    import json as j
    from types import SimpleNamespace

    import charta.web.app as web_app

    payload = j.dumps({"blocks": [
        {"type": "heading", "level": 1, "text": "### Answer"},
        {"type": "facts", "entries": [{"label": "Rent", "value": "900 EUR"}]},
        {"type": "p", "text": "details [f.txt p1]"},
    ]})

    def fake(question, folder, llm_client, steps=None, rounds=5):
        if steps is not None:
            steps.append({"kind": "done", "text": "Answer ready."})
        raw = f"FINAL: {payload}"
        return SimpleNamespace(answer=web_app.structured_answer(raw)[0],
                               blocks=web_app.structured_answer(raw)[1],
                               raw=raw, citations=[],
                               calls=[], used_tools=True, files=["f.txt"])

    monkeypatch.setattr(web_app, "ask_with_tools", fake)
    monkeypatch.setattr(web_app, "answer_query",
                        lambda *a, **k: SimpleNamespace(
                            text="should not be used", citations=[]))
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    body = client.post("/api/ask", params={"folder": str(tmp_path)},
                       json={"q": "what?"}).json()
    done = _wait_job(client, body["job"])
    assert done["state"] == "done"
    types = [b["type"] for b in done["blocks"]]
    assert types == ["heading", "facts", "p"]
    assert "###" not in j.dumps(done["blocks"])
    assert done["blocks"][0]["text"] == "Answer"


def test_the_renderer_builds_blocks_without_parsing_model_markdown():
    """renderBlocks: typed JSON in, styled HTML out — hashes cannot leak."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = """
const fs=require('fs');
const src=fs.readFileSync(process.argv[1],'utf8');
const grab=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b));
const escHtml=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const toast=()=>{};const folder=()=>'';const revealFile=()=>{};
eval(grab('function mdInline(','window.revealCite'));
const out=renderBlocks([
 {type:'heading',level:1,text:'### Rent overview'},
 {type:'facts',entries:[{label:'Total',value:'900 EUR'}]},
 {type:'table',columns:['Month','Paid'],rows:[['2026-03','900 EUR']]},
 {type:'list',items:['point']},
 {type:'p',text:'why **now** [f.txt p1]'}
]);
if(!/<h3>Rent overview<\\/h3>/.test(out))throw new Error('heading broken: '+out.slice(0,120));
if(!/<div class="facts">/.test(out))throw new Error('facts broken');
if(!/<table>/.test(out))throw new Error('table broken');
if(/#{2,6}/.test(out))throw new Error('hashes leak');
if(!/hl-amount/.test(out))throw new Error('amount highlight lost');
console.log('ok');
"""
    js = (pathlib.Path(__file__).parent.parent / "charta" / "web"
          / "static" / "app.js")
    r = subprocess.run([node, "-e", script, str(js)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, f"renderBlocks failed: {r.stderr}"
