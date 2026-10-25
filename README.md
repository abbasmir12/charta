# Charta — Make any folder intelligent

**Right-click any folder in Windows → "Watch with Charta" → the folder files itself.**

Drop anything into it — invoices, lecture slides, scans, receipts — and Charta
reads each file once, renames it, moves it into the right subfolder, and writes a
row about it into a small local index. After that, asking the folder a question
("how much did I spend since January?") reads the **index**, not the pile of
files. Your AI memory is a Markdown file you own and can edit.

*GitHub repo description: Right-click any folder to make it intelligent. Drop files and it auto-organizes, renames, and indexes them. Ask questions like 'how much did I spend since January?' and get answers from the local index. Works with any OpenAI-compatible model (Ollama locally or OpenAI/OpenRouter/etc. in cloud).*

<a href="https://youtu.be/Y1YP2tSMvu4"><img src="https://img.youtube.com/vi/Y1YP2tSMvu4/maxresdefault.jpg" alt="Charta demo — drop invoices into a watched folder and watch it file itself" width="720"></a>

▶ **[Watch the 90-second demo](https://youtu.be/Y1YP2tSMvu4)**

Windows-first, local-first. Default model runtime is a local Gemma through
Ollama — and because the client speaks the standard OpenAI-compatible API, the
same code runs against OpenRouter, Groq, Together, DeepSeek, OpenAI, LM Studio,
llama.cpp or vLLM by editing one config file. No cloud calls unless you point it
at one, and no telemetry. Fonts and icons are bundled — no CDN.

---

## How it works

1. **You name the folder's purpose.** One sentence, typed or spoken: *"freelance
   invoices and receipts for my taxes"*. It becomes a **Folder Charter** at
   `.charta/charter.md` — Markdown with YAML front-matter, human-editable, the
   AI's memory as a file you can open in Notepad.
2. **Everything that lands in the folder is read once.** A stable-file watcher
   waits until the copy finishes, then extracts the text (PDF via PyMuPDF,
   DOCX/XLSX/CSV/TXT, images and scans through a vision model), classifies it
   with a short human reason, and proposes a home: `Invoices/2026/`,
   `Lectures/`, `Insurance/`.
3. **It gets indexed, not re-read.** `.charta/index.db` (SQLite, one file, no
   vector database) gets a row per file: path, description, document type, tags,
   dates, vendor, amounts, and the text of the pages. Ask builds its answers from
   these rows plus BM25 keyword ranking and regex signals for dates, months and
   amounts.
4. **Nothing moves without you.** Suggest mode is the default: you get a list of
   proposed changes with reasons. Approve them and every move is journaled in
   `.charta/journal.jsonl` and committed to a private git history inside the
   folder — one click or `charta undo` puts a file back.
5. **Ask the folder.** The model is handed three tools — `search_index`,
   `read_file`, `list_files` — and answers with citations (file + page) from what
   it found. It refuses to invent an answer when the folder has nothing.

## Try it in 30 seconds (no model needed)

```bash
pip install -r requirements.txt
python -m charta.cli demo        # builds ./charta-demo, sorts it, writes receipts.csv
python -m charta.cli open --folder ./charta-demo   # same folder in the UI
```

The demo writes 8 realistic files, creates a freelancer charter, proposes
placements, approves them, and produces `.charta/outputs/receipts.csv` (plus
`.xlsx` when `openpyxl` is installed). It runs entirely on the offline heuristic
— no model or network required. Add `--ai` to let your configured model classify,
`--preset student|data_entry` for the other outputs, `--watch` to leave the folder
being watched, `--dry-run` to see proposals without moving anything, and `--reset`
to rebuild. Every move is journaled and undoable.

There is also a messier, hand-built sample: `samples/flat-paperwork/` — 27 files
flat at the root (EDF bills with March deliberately missing, Orange invoices, a
lease, rent receipts, an insurance attestation, a bank CSV, photos, a `.docx`
letter, and one sensitive residence permit) for testing the watcher and the
"sensitive file" path.

## Bring your own model provider

Charta talks to **any OpenAI-compatible endpoint** — one client, one code path,
no provider-specific branches. Point `[llm]` at whichever you prefer:

> **One config file, and it is yours.** `config.toml` is git-ignored: it belongs
> to the machine, so `git pull` can never bring back the file you edited. A fresh
> clone ships `config.toml.example` — copy it once:
> `copy config.toml.example config.toml`. `charta testmodel` and `charta doctor`
> print the file in use. Set `CHARTA_CONFIG` to point at a different one.

| Provider | `provider` | default `base_url` |
| --- | --- | --- |
| Ollama (default, local) | `ollama` | `http://localhost:11434/v1` |
| LM Studio (local) | `lmstudio` | `http://localhost:1234/v1` |
| llama.cpp (local) | `llamacpp` | `http://localhost:8080/v1` |
| vLLM (local) | `vllm` | `http://localhost:8000/v1` |
| OpenAI | `openai` | `https://api.openai.com/v1` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` |
| Groq | `groq` | `https://api.groq.com/openai/v1` |
| Together | `together` | `https://api.together.xyz/v1` |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` |
| anything else | `custom` | set `base_url` yourself |

`provider` alone is enough: leave `base_url` blank and it uses the endpoint in
the table. Only set `base_url` for a custom/self-hosted server — a URL that still
points at another provider's stock default is ignored, so flipping `provider`
without touching `base_url` works.

```toml
[llm]
provider = "openai"

[models]
generation = "gpt-4o-mini"
```

Keys stay out of the repo — use env vars instead of the `api_key` field:
`CHARTA_API_KEY` (also picks up `OPENAI_API_KEY` for cloud providers),
`CHARTA_BASE_URL`, `CHARTA_MODEL`. The Settings page edits all of this and writes
it straight to your `config.toml`.

If the endpoint is unreachable Charta never crashes: every call has a timeout
and one retry, then it falls back to heuristics and tells you which provider and
URL failed.

## Quickstart

```bash
pip install -e ".[native]"        # installs the `charta` command + native window
# (dependencies only: pip install -r requirements.txt, then use `python -m charta.cli`)
# default local provider (required for AI; everything degrades gracefully without it)
ollama serve
ollama pull gemma4:e4b            # or whatever `[models] generation` names
```

> Using OpenAI/OpenRouter/Groq instead? Set the env vars, skip Ollama:
> `export CHARTA_BASE_URL=https://api.openai.com/v1 CHARTA_API_KEY=sk-... CHARTA_MODEL=gpt-4o-mini`

```bash
# 1. create a charter
python -m charta.cli charter --folder ./demo --text "receipts and invoices I track for freelance taxes"
# 2. scan + propose (suggest mode: nothing moves until you approve)
python -m charta.cli watch ./demo --scan --once
python -m charta.cli proposals --folder ./demo
python -m charta.cli approve --folder ./demo --all --dry-run   # preview
python -m charta.cli approve --folder ./demo --all             # move + journal
python -m charta.cli undo --folder ./demo                      # undo one move
# 3. gaps + questions + outputs
python -m charta.cli gaps --folder ./demo
python -m charta.cli ask --folder ./demo "what electricity bills for March?"
# 4. UI — Electron desktop app (recommended), pywebview, or your browser
cd desktop && npm install && npm start   # native window, custom title bar, tray
cd ..
python -m charta.cli open ./demo         # pywebview window, or your browser
python -m charta.cli serve --port 8123   # plain local server
python -m charta.cli watchd              # background watcher for every watched folder
python -m charta.cli doctor              # why won't it start? (read-only)
python -m charta.cli testmodel           # ask the model "hello" and print its reply
python -m charta.cli logs                # startup, errors and the exit reason
python -m charta.cli stop                # close the running instance cleanly
```

Right-click integration (Windows, no admin): `charta install-shell`
(Win11: entry under *Show more options*) — it opens the **setup window** for the
folder you clicked. `charta unwatch` stops watching a folder;
`charta uninstall-shell` removes the Explorer entry.

**On Windows, start here:** `python -m charta.cli doctor` prints a read-only
readiness report (provider, icon, pywebview, DWM, shell entry, safety guard).
Then `python -m charta.cli testmodel` sends a one-word prompt end to end and shows
the model's reply with a PASS/FAIL status — the fastest way to prove the AI is
actually wired up. Full runbook and the visual checklist:
[`docs/WINDOWS.md`](docs/WINDOWS.md).

## Safety by default

- **Suggest mode** is the default; `--mode auto` is opt-in per folder, and
  `--dry-run` still moves nothing.
- **Never deletes.** Files are moved or copied; "Move to trash" in the UI is a
  move into `.charta/trash/`, reversible.
- **Undo everything.** `.charta/journal.jsonl` plus a private git history means a
  wrong move is one click or `charta undo` away.
- **Protected paths are refused** (Windows, Program Files, AppData, drive roots,
  your profile root) — including in the web API, with a friendly full-screen page
  instead of an error dump.
- **Sensitive content stays out of the index** by default: ID numbers, card
  numbers, IBANs and passwords are detected, the file is flagged, and its text is
  kept out of search (`[safety] exclude_sensitive_from_index`).
- **Every AI decision carries a reason** in plain language: *"Invoices/2026 —
  electricity bill from EDF dated March 2026."*

## The desktop app (Electron)

`desktop/` is a small Electron shell around the same local UI — no bundler, no
transpiler, the renderer is still the FastAPI HTML. It owns the native chrome:

- **Custom title bar** (`titleBarStyle: 'hidden'` + `titleBarOverlay`) that follows
  the in-app theme toggle, plus **Windows 11 Mica** (`backgroundMaterial`).
- **System tray**: close the window and Charta keeps watching; the tray menu opens
  the app, jumps to Review or Ask, or quits. One taskbar entry via AppUserModelID.
- **Push-to-talk**: `Ctrl+Space` works globally, even from the tray — record,
  transcribe, ask, and get a notification when the answer is ready.
- **Remembered geometry** in the same `window.json` the CLI uses.
- **No browser chrome**: F5 / Ctrl+R / Ctrl+F / Ctrl+P / DevTools are blocked in
  `before-input-event` (and again in the renderer), unless `npm run debug`.
- **Hardened by default** per Electron's security checklist: `contextIsolation`,
  `sandbox`, `nodeIntegration: false`, a tiny `contextBridge` API, navigation and
  `window.open` limited to local URLs (links open in your real browser).

```bat
cd desktop
npm install
npm start            :: run the app
npm run debug        :: keep browser keys + DevTools
npm test             :: unit-test the shell helpers (no display needed)
npm run smoke         :: load every screen headlessly and fail on console errors
npm run shots         :: write docs/screenshots/electron-*.png
```

The shell never touches your files: it starts `charta serve` on a free port, waits
for `/api/health`, and everything else goes through the same guarded core.

## Native-feel polish

`charta open` (and the Electron app) is meant to feel like an app, not a tab:

- **Dark title bar** via the DWM API (`DWMWA_USE_IMMERSIVE_DARK_MODE`) and
  **Windows 11 Mica** (`DWMWA_SYSTEMBACKDROP_TYPE`), with a solid title-bar color
  fallback when Mica is unavailable (`[app] mica = false` disables the attempt).
- **AppUserModelID** + a real **multi-size `.ico`** (16→256 px) for the title bar,
  alt-tab, taskbar and Explorer entry — regenerate it any time with
  `python3 tools/make_icon.py`.
- **Remembered window geometry** (`%APPDATA%/Charta/window.json`), guarded against
  off-screen or unusable sizes.
- Browser chrome is taken away: no context menu, and F5 / Ctrl+R / Ctrl+F / Ctrl+P /
  F12 / DevTools are swallowed. `charta open --debug` (or `--debug` on `serve`)
  gives them all back for development.
- `user-select: none` on app chrome (only content is selectable),
  `overscroll-behavior: none`, and thin themed scrollbars.
- Custom in-app dropdowns and a custom **folder picker** (folders only, keyboard
  navigable) instead of native `<select>` and a raw path box. Protected locations
  stay visible but can't be picked — you get a friendly refusal screen, not an error dump.

## What works today

- Charter create/load/edit + 3 presets (student, freelancer, data_entry), typed or spoken
- Extractors (txt/md/csv/xlsx, PDF via PyMuPDF, docx) + **vision** for images and
  scanned PDFs (any vision-capable model; text is redacted before it is stored)
- Stable-file watcher, classification (model JSON or heuristic fallback) with human reasons
- **Suggest mode and auto mode** (`--mode auto`, opt-in per folder; `--dry-run` still moves nothing).
  Both modes go through one pipeline: protected-path refusal, journal + undo, collision suffix.
- Approve/reject, mover (dry-run, `(2)`-suffix collisions), journal + undo
- Receipts xlsx+csv, study notes+flashcards, data-entry table
- Gap detection, ask-with-citations (refuses to invent), sensitive-file guard
- **A metadata index per folder** (`.charta/index.db`, SQLite): every file Charta
  reads gets a row with its description, type, tags and the fields in it
  (date, vendor, amount). Ask works from that index instead of re-reading the
  folder, and **Search** finds files by name, tag, description or content
- **The model calls tools**: Charta hands the model a catalogue of the index and
  three tools — `search_index`, `read_file`, `list_files` — and it uses them
  itself, so the answer comes from the folder's metadata and the files that
  matter. Every call is shown in the timeline; a model that ignores the tools
  still gets a grounded answer
- **A work timeline in Ask**: every step as it happens (read the index → matched
  N files → asking provider/model → answer), with a persisted chat per folder
  (`.charta/chats/<id>.json`) so "and what about June?" works
- **Search** (`/search`): clickable results with the metadata that matched —
  open in the system app, read in place, or ask about that file
- **Folders dashboard**: every folder Charta knows, how many are watched, what is
  in each one, an ask box per folder, and pause/resume that keeps the analysis
- **Files view**: every file with its index state and reason, a reader (text,
  PDF, DOCX, vision summary), in-place editing that keeps the old version, and
  "Move to trash" (reversible — nothing is ever deleted)
- **Git history per folder**: a private repo in `.charta/git` records every
  index, move, edit and rebuild with a readable message; `git log` works in
  your own terminal, and an old version of a file can be restored with a click
- **Bulk scans with progress**: scanning a folder with hundreds of files runs in
  the background and shows what it is working on
- **Real watching that survives the window**: a per-user watched-folders registry
  plus a background watcher hosted by the local backend, so closing to the tray
  keeps the folder watched. Overview shows lane status, Scan now, and Stop watching
- **Shell integration**: right-click "Watch with Charta" in Explorer, a live tray
  menu, and per-folder "Being watched with Charta" verbs
- Web UI (setup / folders / overview / files / search / review / outputs / gaps /
  ask / activity / history / settings / styleguide), SSE live strip, voice input
  (Web Speech in the browser, faster-whisper locally in the CLI, ElevenLabs as an
  opt-in cloud option) and push-to-talk with an answer-ready notification
- **Design system with tests**: WCAG-AA-checked palette (both themes), 4px spacing
  scale, 7-step type scale, and every `var(--token)` proven defined — `tests/test_design.py`
- **Measured UI checks**: `tools/ui_check.py` drives all 12 routes in three passes
  (1280 dark/light, 900 narrow) and fails on horizontal overflow, missing `h1`,
  targets under 24px, or console errors; it also writes `docs/screenshots/`
- **Diagnosable startup**: everything goes to `<state>/charta.log`, a session file
  records the running instance, and a busy port is recovered instead of aborting
- **Optional Sentry Agent Tracing**: `[observability] sentry_dsn` wraps ask in
  `gen_ai.invoke_agent` / `chat` / `execute_tool` spans with token usage and
  latency. Silent no-op without a DSN — nothing leaves the machine by default

## Known limits

- Learned rules from corrections, the weekly digest and the deadline timeline are
  planned, not built (the charter, index and history they need are in place).
- The watcher reacts to files **arriving**; a file you move out yourself in
  Explorer is not journaled. Charta only records the changes it makes.
- The Windows-only visuals (Mica, tray icon rendering, Explorer verb) are
  implemented and unit-tested as guarded no-ops; the final visual pass on a real
  Windows machine is ongoing, so `charta open` falls back to your browser if
  `pywebview` is missing.
- Vision quality depends entirely on the model you point it at (a 4B local Gemma
  is rough on handwriting; a bigger or cloud vision model does much better).
- ElevenLabs STT is implemented but off by default — it is a cloud call and
  labelled as one.
- Ask is lexical (BM25 + regex + per-file descriptions), not embedding-based. It
  is fast and needs no second model, but pure paraphrase questions can miss.

## Requirements

Python 3.11+ on Windows 10/11 (core stays cross-platform and passes on Linux CI).
`pip install -r requirements.txt` covers the app; `[native]` adds pywebview,
`[sentry]` adds tracing. Ollama (or any compatible endpoint) is only needed for
the AI paths — extraction, proposals, outputs, gaps and the demo work offline.
For the desktop shell: Node + `npm install` in `desktop/`.

## Performance (measured on this machine, 2026-10-25)

- Heuristic classify: <0.1 ms/file; eval accuracy on 5 canonical samples: **5/5 (100%)**
- `pytest -q`: **287 passed** in ~22 s (includes a fake OpenAI-compatible server, so no provider is needed)
- `npm test` (shell helpers): **9 passed** in ~0.16 s; `npm run smoke` loads every route headlessly and fails on any console error (needs a display)
- `tools/ui_check.py`: **36 screens** (12 routes × 3 passes) measured and screenshotted in ~25 s — last run: all passed, no console errors
- `charta doctor`: read-only, <0.5 s, no writes to your folders
- Icon generation (`tools/make_icon.py`): 7 sizes, ~0.3 s, 19 KB — stdlib only
- LLM timings with a live provider: TBD — record `time charta demo --ai` on your laptop and update STATUS.md

## Screenshots

`docs/screenshots/` holds every screen in both themes — setup, folders,
overview, files, review, outputs, gaps, ask, activity, history,
settings, the styleguide — plus nine Electron shell shots. They are generated,
not hand-drawn, by `tools/ui_check.py` and `npm run shots`, and double as the
visual regression baseline for the demo video.

## Docs and layout

- [`STATUS.md`](STATUS.md) — what works, what is next, decisions, failures
- [`DESIGN.md`](DESIGN.md) — design system the UI must follow
- [`docs/WINDOWS.md`](docs/WINDOWS.md) — Windows + desktop runbook
- [`AGENTS.md`](AGENTS.md) — the rulebook (safety rules, config rules, tests)
- [`DEVPOST.md`](DEVPOST.md) — the submission post, with the demo video

```text
charta/
  core/      charter, watcher, index_db, ask, agent/tools, classify, proposals,
             mover, journal, history, outputs/, gaps, sensitive, llm, config,
             pipeline, demo, watchd, observability, doctor
  voice/     stt (faster-whisper locally; ElevenLabs opt-in)
  web/       FastAPI app + plain HTML/CSS/JS (no bundler, no CDN)
  shell/     Windows registry verbs, pywebview window, desktop launcher
  cli.py     the `charta` command
desktop/     Electron shell (main.js, preload.js, lib/, test/)
tools/       make_icon.py, make_flat.py, ui_check.py
samples/     generated demo data (27 flat files, 3 presets)
tests/       pytest suite (287 tests)
```
