# STATUS.md — Charta live progress log

> Protocol: see AGENTS.md §6. Update IMMEDIATELY after each task.
> Never batch, never start next task before STATUS reflects the last.
> One commit per task; hash goes in Done Log.

## Current Focus

UI/UX refresh landed: a light **dim-white** default theme, one calm indigo accent
(the purple→cyan gradient is gone), an inlined Lucide icon set, and a calmer,
professional layout (120 py + 6 node green; 27 browser + 9 Electron screens
verified in light and dark).

## Milestones

- [x] M0 Scaffold: repo, AGENTS.md, STATUS.md, config, CLI skeleton, provider health check, one passing test.
- [x] M1 Charter: create from text via model, charter.md w/ YAML front-matter, load/edit, 3 presets. Extractors (PDF/images/txt/docx). Stable-file watcher.
- [x] M2 Classification & proposals: model propose dest+name+reason; list/approve/reject; mover; undo journal; dry-run; collision suffix; protected-path refusal. Safety-rule tests.
- [x] M3 Purpose outputs: receipts xlsx+csv; study notes+flashcards; data-entry table; auto-update on approve.
- [x] M4 Gap detection: expected-vs-found report; UI + CLI.
- [x] M5 Ask the folder: chunk/embed/retrieve; cited answers; refuse-to-invent.
- [x] M6 UI, voice, shell:
  - [x] M6.1 tokens.css, fonts, icons, /styleguide
  - [x] M6.2 app shell (sidebar, topbar, palette, theme)
  - [x] M6.3 setup window w/ voice + charter cards
  - [x] M6.4 Review screen w/ keyboard + fly animation
  - [x] M6.5 Outputs, Gaps, Ask (+drawer), Activity, Settings
  - [x] M6.6 empty/loading/error/provider-offline states
  - [x] M6.7 a11y + reduced-motion pass
  - [x] M6.8 screenshots → docs/screenshots: 27 screens verified (desktop 1280px dark+light, narrow 900px dark) by tools/ui_check.py + 9 Electron-window screens by `npm run shots`
  - [x] M6.9 shell install/uninstall + voice wiring
  - [x] M6.10 native-feel polish: window host, DWM dark title bar + Mica (solid fallback), AppUserModelID, multi-size .ico, remembered geometry, browser-key guards with `--debug`, chrome `user-select`, thin themed scrollbars, custom dropdowns + folder picker
  - [x] M6.12 Electron desktop shell + design system: custom title bar (titleBarOverlay) following the theme, Mica, tray with close-to-tray, single instance, AppUserModelID, shared window.json geometry, `before-input-event` shortcut blocking, contextIsolation/sandbox/contextBridge hardening; token system with type/space scales; contrast-checked themes; appbar app shell; sortable output grid; `tools/ui_check.py` measures every screen and `tests/test_design.py` gates the design system
  - [x] M6.13 Silent-exit fix: file logging + session file (`charta logs`), busy-port recovery, browser fallback when the window dies early, `--strict-port` to opt out
  - [x] M6.11 Windows-readiness hardening: ctypes prototypes (no 64-bit handle truncation), DWM attribute-19 fallback, quoted + cwd-independent Explorer command, pywebview kwarg compatibility, `charta doctor`, docs/WINDOWS.md runbook
  - [x] M6.14 UI/UX refresh: dim-white default theme + refined dark, one calm indigo accent (gradient removed), inlined Lucide icon set (`web/icons.py` + `tools/fetch_icons.py`), professional spacing/type (system stack), entrance/skeleton/mic motion; Electron chrome mirrors the theme
- [x] M7 Polish: sample-data generator, README (+screenshots/GIF, Why-local, perf), eval script + baseline, demo run-through.
- [x] M8 Any-provider AI: OpenAI-compatible `LLMClient` (Ollama / LM Studio / llama.cpp / vLLM / OpenAI / OpenRouter / Groq / Together / custom), env-var keys, vision for images + scanned PDFs, auto-mode apply loop behind one shared pipeline. Tests: fake OpenAI-compatible server + vision + pipeline.

## Done Log (newest first)

- 2026-10-17 10:19 UTC, M6.14 UI/UX refresh; files: charta/web/{app.py,icons.py,static/tokens.css,static/app.css,static/app.js}, tools/fetch_icons.py, desktop/main.js, DESIGN.md, docs/screenshots/*, STATUS.md; verified: `pytest -q` 120 passed, `npm test` 6 passed, `python3 tools/ui_check.py` 27/27 screens OK (desktop 1280 dark+light, narrow 900; 0 console errors, 0 overflow, 0 small targets), `xvfb-run npx electron . --smoke` 9/9 routes, `npm run shots` 9 Electron screens; commit (this).
- 2026-10-14 10:05 UTC, STATUS record for M6.12 + M6.13 (this commit); files: STATUS.md; verified: `pytest -q` 120 passed, `npm test` 6 passed, `python3 tools/ui_check.py` 27/27 screens OK, `npm run shots` 9 Electron screens; commit (this).
- 2026-10-14 10:00 UTC, M6.12 Electron desktop shell + measured design system; files: desktop/{package.json,main.js,preload.js,lib/backend.js,lib/paths.js,lib/window-state.js,test/unit.test.js}, charta/web/{app.py,static/tokens.css,static/app.css,static/app.js}, tests/test_design.py, tools/ui_check.py, docs/screenshots/*, README.md, DESIGN.md, docs/WINDOWS.md, AGENTS.md; verified: `pytest -q` 107 passed, `npm test` 6 passed, `npm run smoke` 9/9 routes ok, `python3 tools/ui_check.py` 18/18 screens OK, `npm run shots` 9 Electron screens; commit c3bcc67.
- 2026-10-14 09:55 UTC, M6.13 silent-exit fix; files: charta/core/applog.py, charta/shell/desktop.py, charta/cli.py (`logs`, `--browser`, `--strict-port`), tests/test_runtime.py; verified: busy-port recovery reproduced live (8155 in use → picked 44019, logged), log + session files written, `pytest -q` green; commit c3bcc67.
- 2026-10-14 09:50 UTC, published to GitHub `abbasmir12/charta` over SSH; remote was empty, pushed `main` (14 commits) and set upstream; files: none (repo metadata) + this STATUS entry; verified: `git push -u origin main` exit 0, `git ls-remote origin` → `refs/heads/main 3623c74`, `git status -sb` → `## main...origin/main` (in sync); published commit 3623c74.
- 2026-10-14 09:40 UTC, STATUS record for M6.11 (this commit); files: STATUS.md; verified: `git log -1`; commit (this).
- 2026-10-14 09:35 UTC, M6.11 Windows-readiness hardening + doctor; files: charta/shell/native_window.py (ctypes prototypes, attribute-19 fallback, `dwm_available`, exported `ICON_PATH`), charta/shell/desktop.py (`supported_kwargs`, `window_kwargs`, TypeError retry), charta/shell/windows_registry.py (quoted/cwd-independent `right_click_command`, `_launcher`), charta/core/doctor.py (new), charta/core/config.py (`config_path`), charta/cli.py (`doctor`), docs/WINDOWS.md (new), pyproject.toml (`.native` extra), README.md, tests/test_windows_paths.py (new); verified: `pytest -q` 66 passed, `charta doctor` prints an honest report and exits 1 with no provider, printed the exact HKCU command it would write; commit 7a95670.
- 2026-10-14 09:15 UTC, M6.10 native-feel polish + window host; files: charta/shell/native_window.py (new), charta/shell/desktop.py (new), charta/shell/windows_registry.py, charta/core/fsbrowse.py (new), charta/core/config.py, charta/cli.py (`open`, `--debug`, status line), charta/web/app.py (debug flag, favicon, /protected, /api/fs/list, charter mode + 403, dropdown/picker helpers), charta/web/static/{app.js,app.css,tokens.css}, charta/assets/charta.ico (new), tools/make_icon.py (new), config.toml, requirements.txt, README.md, DESIGN.md, AGENTS.md, tests/{test_native_window,test_fsbrowse,test_web_ui}.py (new); verified: `pytest -q` 59 passed, `eval/eval_classifier.py` 5/5, live `charta open` + curl (setup page has picker and zero `<select>`, `/api/fs/list` lists folders only, `/api/charter` on `C:\Windows` → 403, `/favicon.ico` → 19106-byte ICO, `--debug` flips `window.__CHARTA_DEBUG__` to true, status shows the window mode); commit e3523d0.
- 2026-10-14 08:52 UTC, M8 any-provider AI + vision + auto mode; files: charta/core/llm.py (rewritten as `LLMClient`), config.py, config.toml, cli.py, web/app.py, ask.py, charter.py, classify.py, extract/__init__.py (vision hook), new core/pipeline.py, new tests/{conftest,test_openai_compat,test_extract,test_pipeline}.py, tests/test_config_llm.py, tests/test_features.py, AGENTS.md §§2/4, README.md, .gitignore; verified: `pytest -q` 42 passed; `eval/eval_classifier.py` 5/5; live CLI run against a fake OpenAI-compatible server (status/charter/watch/proposals/ask/auto-mode/undo all correct, `Authorization: Bearer` + `/v1/*` routes observed in the server log); TestClient smoke of all 10 UI routes + /api/health + /api/charter + /api/ask; commit 634802b.
- 2026-10-13 09:05 UTC, STATUS record + UI smoke test, all 9 routes 200 (/, styleguide, overview, review, gaps, ask, activity, settings, api/health) via TestClient; files: STATUS.md; verified: smoke script; commit (this).
- 2026-10-13 09:00 UTC, M7 Polish, sample generator (3 presets), eval_classifier 5/5=100%, honest README (works/doesn't-work/perf); files: samples/generate.py, eval/eval_classifier.py, README.md; verified: `python3 eval/eval_classifier.py` → 5/5; commit c36a10e.
- 2026-10-13 08:55 UTC, M6 UI/voice/shell, FastAPI app + tokens/app.css/app.js + 8 screens + SSE + palette + registry + STT interface; files: charta/web/*, charta/voice/stt.py, charta/shell/windows_registry.py, charta/cli.py; verified: pytest 18/18 + route smoke; commit 30339c9.
- 2026-10-13 08:50 UTC, M3–M5 outputs/gaps/ask, receipts xlsx+csv, study notes+flashcards, data-entry table, gap ranges+months, hash-embed fallback retrieval with refusal; files: charta/core/outputs/__init__.py, gaps.py, ask.py, tests/test_features.py; verified: test_features.py 6/6; commit 1f50b2a.
- 2026-10-13 08:45 UTC, M2 safety core, heuristic+LLM classify, proposals store, mover (dry-run/suffix/traversal-guard), journal undo, protected paths, sensitive regex; files: 6 core modules + tests/test_safety.py (8 tests); verified: pytest; commit 3f88a5e.
- 2026-10-13 08:40 UTC, M1 charter+extract+watch, presets, md+YAML round-trip, LLM JSON w/ fallback, PyMuPDF/docx/text interface, wait_stable+watchdog; files: charter.py, extract/, watcher.py, test_charter.py; verified: pytest; commit bb62eff.
- 2026-10-13 08:35 UTC, M0 scaffold, config.toml loader, Ollama client (timeout+retry+fallback), pytest baseline; files: config.toml, pyproject.toml, requirements.txt, config.py, llm.py, test_config_llm.py; verified: `pytest -q` green; commit 7bb7038.
- 2026-10-13 08:30 UTC, STEP 0 bootstrap, AGENTS.md + STATUS.md + DESIGN.md; verified: git log; commit 6db9d12.

## In Progress

- Task: live-provider timing/quality (Ollama or a cloud model) on a real laptop.
- Plan: with a live endpoint, `time charta watch --scan` + record s/file and model tag; run the same on a scanned PDF to grade vision quality.
- Remains: real-model numbers; Windows run of the Electron window.

## Next Up

1. Windows run of the desktop app: `cd desktop && npm install && npm start` — walk `docs/WINDOWS.md` §7 and send back `charta logs` if anything misbehaves.
2. Live-provider pass: JSON-validity rate + s/file for Ollama (gemma3:4b) and one cloud vision model on the scanned-PDF sample.
3. Package the desktop app (electron-builder) so it ships as an installer instead of `npm start`.

## Blockers & Open Questions

- No live provider on this box → the OpenAI-compatible path is verified against a local fake server (tests/conftest.py) plus a manual CLI/UI run; real-model timing and vision quality still TBD.
- Native window (DWM dark title bar, Mica, .ico, AppUserModelID, geometry, pywebview host) is written and unit-tested as a guarded no-op, but never executed on Windows: the visual result is unverified. Same for `charta install-shell` after it switched to launching `charta open`.
- The Electron shell is verified headlessly under Xvfb on Linux (backend lifecycle, 9 routes, screenshots) but never on a real display: the custom title bar, Mica, tray icon and close-to-tray behaviour need a Windows run. No installer is produced yet (electron-builder not added).
- Fonts not yet bundled (Inter/JetBrains Mono pending) — CSS falls back to system fonts; no CDN used (good).
- Open question: should `provider` send an "OpenRouter-*" attribution header? Bot-blocking providers may want it; not needed for local use.
- Open question: bundle pywebview as a default dependency? Currently optional so the web UI keeps working with zero extra installs.

## Decisions

- 2026-10-17: Switch to a light-first **dim-white** theme with one calm indigo accent and drop the purple→cyan gradient. Why: the gradient + dark glass read as "AI-generated"; a near-neutral palette, hairline borders and a single accent read as a professional desktop tool, and dim white (not pure #fff) is easier on the eyes. Dark stays as a toggle.
- 2026-10-17: Bundle Lucide as inlined SVG in `web/icons.py` (generated by `tools/fetch_icons.py`) instead of emoji/unicode glyphs. Why: emoji render differently on every OS and look unfinished; one inline stroke-icon set keeps the UI coherent and still ships locally with no CDN.
- 2026-10-17: Use the Windows system UI font stack (Segoe UI Variable → system-ui) instead of downloading Inter. Why: it is already the native Windows typeface, needs no binary files in the repo, and keeps "no CDN / no bundled fonts" true.
- 2026-10-14: Electron hosts the existing FastAPI UI rather than replacing it. Why: the renderer stays plain HTML/CSS/JS (no bundler, no rewrite), Electron only owns native chrome — title bar, tray, shortcuts, lifecycle — and the UI still runs in a browser when Node is absent. Recorded as an explicit exception to the old "no heavy build step" rule in AGENTS.md.
- 2026-10-14: Treat measurable UI properties as the definition of "professional": WCAG contrast on the real palette, 4px spacing grid, 24px minimum hit targets, one h1 per screen, no horizontal overflow, no console errors. Why: a claim about visual quality cannot be verified, but these can, and they caught two real defects on the first run.
- 2026-10-14: Closing the Electron window hides to the tray instead of quitting. Why: Charta watches folders in the background; quitting on close would silently stop the watcher, which is the behaviour the user reported as a bug.
- 2026-10-14: Every run logs to `<state>/charta.log` and records `<state>/session.json`. Why: the original "closes by itself" report was undiagnosable because the console died with the message.
- 2026-10-14: Recover from a busy port by choosing a free one instead of aborting. Why: a stale instance holding 8123 was the most likely silent-exit path, and refusing to start is worse than moving ports.
- 2026-10-14: Declare explicit ctypes `restype`/`argtypes` for `LoadImageW`/`SendMessageW`/`DwmSetWindowAttribute`. Why: undeclared HANDLE/HWND return types truncate to 32 bits on 64-bit Python, so the icon and DWM calls would have silently targeted the wrong window — this would have looked like "Windows polish just doesn't work".
- 2026-10-14: Try DWM attribute 20 then 19 for the dark title bar. Why: builds before Win10 2004 reject 20, and a rejected attribute is indistinguishable from "feature not supported" in a bug report.
- 2026-10-14: Filter pywebview kwargs through `inspect.signature` with a TypeError retry. Why: `maximized`/`background_color` don't exist in older pywebview, and an unknown kwarg kills the window before it opens.
- 2026-10-14: The Explorer entry bootstraps the repo on `sys.path` instead of `python -m charta.cli`. Why: registry commands start with an arbitrary working directory, so `-m` only worked when Charta was pip-installed; quoting is also explicit now that paths contain spaces.
- 2026-10-14: Ship `charta doctor` (read-only) rather than a longer troubleshooting doc. Why: the Windows run is unverified, so the fastest path is one command whose output can be pasted back for triage.
- 2026-10-14: Add a real window host (`charta open`, pywebview optional) instead of stubbing the native polish. Why: dark title bar, Mica, taskbar identity and remembered geometry need a window handle; a browser tab makes the whole checklist unreachable.
- 2026-10-14: Keep `sys.platform != "win32"` guards around every ctypes call and unit-test them as no-ops. Why: the core must pass on Linux CI, and the guard behaviour is the only part of DWM we can actually test here.
- 2026-10-14: Right-click Explorer entry now launches `charta open` (setup window for that folder) rather than `charta watch`. Why: DESIGN.md screen 1 says the setup window opens from right-click; `watch` stays for the always-on daemon.
- 2026-10-14: Generate the .ico from code (`tools/make_icon.py`, stdlib zlib/struct) instead of committing hand-drawn art. Why: no binary assets to lose, every size stays in sync, and it doubles as the favicon.
- 2026-10-14: `--debug` is resolved per request from config/env rather than at import time. Why: uvicorn imports the app by string in a thread, so import-time flags would be stale.
- 2026-10-14: Protected folders stay *browsable* in the picker but cannot be selected, and `/api/charter` returns 403 with a friendly refusal page. Why: refusing to even show a location feels broken; refusing to act on it is the safety rule.
- 2026-10-14: One OpenAI-compatible `LLMClient` for all providers instead of an Ollama-only path. Why: "bring your own model" must not mean editing client code; Ollama, LM Studio, OpenAI, OpenRouter, Groq and friends all speak the same three routes.
- 2026-10-14: Keys come from env (`CHARTA_API_KEY`, `OPENAI_API_KEY` for cloud providers), never required in the repo. Why: a config file that gets committed is the wrong place for a secret.
- 2026-10-14: `json_mode` uses `response_format: json_object` and retries *without* it on HTTP 400/422. Why: faithful to the OpenAI schema, but some compatible servers reject the field; the retry keeps them working.
- 2026-10-14: Vision is on by default and rides the same client; transcription is redacted before it is stored/indexed. Why: scanned PDFs/screenshots are a headline feature, and sensitive content must not enter the index even via OCR.
- 2026-10-14: New `core/pipeline.py` owns "new file → propose → maybe move" so suggest and auto mode share exactly one safety path. Why: auto mode must not be a second, laxer code path.
- 2026-10-13: Stack = FastAPI+vanilla JS, SQLite+blobs (deferred — ask currently in-memory index; SQLite lands if >1k files), watchdog, PyMuPDF-optional, openpyxl, faster-whisper-optional. Why: zero-build UI, graceful degradation, laptop-friendly.
- 2026-10-13: Suggest-mode default, journal+undo, dry-run, no-delete enforced in core (not just UI). Why: safety rules non-negotiable + demo trust story.
- 2026-10-13: Fonts/icons bundled-locally policy, no CDN. Why: "100% local" must include UI assets.
- 2026-10-13: Heuristic fallback for classify/ask when the model is down (hash embeddings, regex outputs). Why: demo must survive a dead provider; tests deterministic.
- 2026-10-13: urllib (stdlib) for provider HTTP instead of httpx/requests. Why: fewer deps, full timeout control — still true for the OpenAI-compatible client.
- 2026-10-13: Grouped M3–M5 in one commit (outputs/gaps/ask share tests). Why: 5-day deadline; noted here, history still per-milestone.

## Failures & Lessons

- 2026-10-17: The setup screen nested the folder `Choose folder…` button *inside* a `.chip` (a button in a pill) — cramped and unclickable-looking. Caught by reading the rendered screenshot. Fixed by splitting it into a `.setup-row`: a mono path chip + a separate button. Lesson: render and *look*; markup that validates can still look wrong.
- 2026-10-17: In the narrower 3-up overview cards the mode chip shrank to "Suggest mod". Fixed by giving `.card-head h3` `min-width:0` (the title wraps) and the chip `flex:0 0 auto`. Lesson: flex children shrink by default — decide which one is allowed to.
- 2026-10-14: The new contrast test failed the light theme immediately: `--warning` (#FBBF24) sat at ~1.6:1 on white because the light theme never redefined the semantic colours. Fixed by adding darkened light-theme accents. Lesson: a second theme is not a background swap — every semantic colour needs its own check.
- 2026-10-14: `tools/ui_check.py` found clickable chips and sort headers at 22px, under the 24px WCAG 2.2 target minimum. Fixed with `button.chip` and `.sort-btn` hit areas. Lesson: measuring the rendered DOM beats eyeballing a stylesheet.
- 2026-10-14: `port_is_free()` used `SO_REUSEADDR`, which on Linux lets a bind succeed against a socket that is bound but not listening — so a half-dead instance looked free. Caught by my own new test; fixed to probe for a listener first, then bind without SO_REUSEADDR. Lesson: a passing smoke test is not a passing correctness test.
- 2026-10-14: `node --test test/` reported the directory as one failing test. The working invocation is plain `node --test`. Lesson: fix the invocation, not the test.
- 2026-10-14: `console-message` with the old `(event, level, message)` signature is deprecated in Electron 44; switched to the single event object so the warning does not mask real ones.
- 2026-10-14: Reviewing the Windows path *before* the first Windows run turned up four defects that tests on Linux could never have caught: undeclared ctypes prototypes (64-bit handle truncation), a single DWM attribute id, unquoted paths in the Explorer command, and pywebview kwargs that older releases reject. Lesson: "guarded no-op on Linux" verifies the guard, not the behaviour — read the platform-specific branch as if it were the only branch.
- 2026-10-14: Wrote `assert provider.ok is False and "ollama" in hint or provider.ok` — an `and`/`or` precedence slip that made the assertion almost always true. Rewrote it to assert the actual expected state. Lesson: an assertion that can pass for the wrong reason is worse than none.
- 2026-10-14: Found a real safety gap while wiring the picker — the web API (`/api/charter`) never called `assert_not_protected`, so the UI could write a charter into `C:\Windows` even though the CLI refused. Fixed and covered by a 403 test. Lesson: when two entry points share core code, check *each* entry point for the guards, not just the one with tests.
- 2026-10-14: The folder-picker test failed because `roots` was only populated when a path was missing. Fixed the behaviour (drive roots are always offered so the picker can switch drives) rather than relaxing the assertion. Lesson: a test that catches an inconsistent return shape is doing its job.
- 2026-10-14: Left `bytes(...) if False else rgba` in the new PNG encoder — a placeholder expression that would have shipped silently. Caught on read-back before running the generator. Lesson: same failure mode as the earlier `.feed if False` bug; re-read new files before executing them.
- 2026-10-14: `charta open` looked like it printed nothing in the log; stdout was block-buffered to a file, so the fallback message was lost on kill. Re-ran with `PYTHONUNBUFFERED=1` to actually confirm the user-facing message. Lesson: "no output" can be buffering, not a bug — but verify instead of assuming.
- 2026-10-14: Wrote a placeholder test that asserted nothing real (`img = fake_provider` reused as a path). Caught on read-back before `pytest` ran; rewritten to attach a real image and assert the data-URI part. Lesson: an assertion you can't explain is a bug, not coverage.
- 2026-10-14: Adding images to `build_index` initially indexed `[image file: x.png]` stub text when no vision model was configured. Fixed by skipping `image-stub` results. Lesson: widening an extractor's input set means revisiting what the *unavailable* path produces.
- 2026-10-13: Wrote `open(flash_path, ".feed" if False else flash_path, ...)` — nonsense mode arg in build_study (leftover edit). Caught on read-through before tests ran; fixed to plain `"w"`. Lesson: re-read new files before testing; 18/18 after fix.
- 2026-10-13: `pip install` blocked by PEP 668 (externally-managed env); fixed with `--break-system-packages`. Lesson: check env first on Kali.
- 2026-10-13: Assumed pytest present; it wasn't. Lesson: verify test runner in M0 before writing tests.

## How to Run & Test

```bash
git clone git@github.com:abbasmir12/charta.git   # remote: git@github.com:abbasmir12/charta.git
cd charta
python3 -m pytest -q                       # 120 passed
python3 tools/ui_check.py                  # 27 screens measured + docs/screenshots/
python3 tools/fetch_icons.py               # regenerate charta/web/icons.py (needs network)
cd desktop && npm test && npm run smoke    # 6 unit tests; 9 screens headless
xvfb-run -a npx electron . --smoke --folder=/tmp/demo   # headless Electron smoke (CI)
cd desktop && npm start                    # the desktop app
python3 -m charta.cli doctor               # readiness report (read-only)
python3 -m charta.cli logs                 # log tail + running session
python3 eval/eval_classifier.py            # 5/5 = 100%

# default provider: local Ollama
ollama serve && ollama pull gemma3:4b && ollama pull nomic-embed-text

# any OpenAI-compatible provider, no code change (env wins over config.toml)
export CHARTA_BASE_URL=https://api.openai.com/v1 CHARTA_API_KEY=sk-... CHARTA_MODEL=gpt-4o-mini

python3 -m charta.cli status --folder ./demo            # shows provider + reachability
python3 -m charta.cli charter --folder ./demo --text "receipts and invoices I track for freelance taxes"
python3 -m charta.cli watch ./demo --scan --once        # suggest mode (default)
python3 -m charta.cli watch ./demo --scan --once --dry-run   # auto mode, moves nothing
python3 -m charta.cli proposals --folder ./demo
python3 -m charta.cli approve --folder ./demo --all --dry-run
python3 -m charta.cli undo --folder ./demo
python3 -m charta.cli gaps --folder ./demo
python3 -m charta.cli ask --folder ./demo "what electricity bills for March?"
python3 -m charta.cli serve --port 8123   # UI: http://127.0.0.1:8123/overview?folder=./demo
python3 -m charta.cli doctor              # read-only readiness report (exit 1 if not ready)
python3 -m charta.cli doctor --json | python3 -m json.tool
python3 -m charta.cli open ./demo         # native window (pywebview) or browser fallback
python3 -m charta.cli open ./demo --debug # keep F5/Ctrl+R/F/P + DevTools while developing
python3 tools/make_icon.py                # regenerate charta/assets/charta.ico (7 sizes)
python3 -m charta.cli status --folder ./demo   # also prints the window mode
```
