# Charta — your messy folder quietly sorts itself

Windows-first, local-first. Right-click any folder → **Watch with Charta** →
answer *"What is this folder for?"* (text or voice). A local Gemma model
writes a **Folder Charter** (`.charta/charter.md`, human-editable), and from
then on the folder understands itself: proposes organization, builds
purpose-specific outputs, flags gaps, answers questions with citations.

**Local by default:** all models run on your machine. No cloud calls —
including UI assets (fonts/icons bundled, no CDN).

## Try it in 30 seconds (no model needed)

```bash
pip install -r requirements.txt
python -m charta.cli demo        # builds ./charta-demo, sorts it, writes receipts.csv
python -m charta.cli open --folder ./charta-demo   # same folder in the UI
```

The demo writes 8 realistic files, creates a freelancer charter, proposes
placements, approves them, and produces `.charta/outputs/receipts.csv`. It runs
entirely on the offline heuristic — no model or network required. Add `--ai` to
let your configured model classify, `--preset student|data_entry` for the other
outputs, `--dry-run` to see proposals without moving anything, and `--reset` to
rebuild. Every move is journaled and undoable.

## Bring your own model provider

Charta talks to **any OpenAI-compatible endpoint** (one code path, no code
changes). Point `[llm]` in `config.toml` at whichever you prefer:

| Provider | `provider` | default `base_url` |
| --- | --- | --- |
| Ollama (default, local) | `ollama` | `http://localhost:11434/v1` |
| LM Studio (local) | `lmstudio` | `http://localhost:1234/v1` |
| llama.cpp / vLLM (local) | `llamacpp` / `vllm` | `http://localhost:8080/v1` |
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
generation_model = "gpt-4o-mini"     # [models] section
```

Keys stay out of the repo — use env vars instead of the `api_key` field:
`CHARTA_API_KEY` (also picks up `OPENAI_API_KEY` for cloud providers),
`CHARTA_BASE_URL`, `CHARTA_MODEL`.

If the endpoint is unreachable Charta never crashes: it falls back to
heuristics and tells you which provider and URL failed.

## Quickstart

```bash
pip install -e ".[native]"        # installs the `charta` command + native window
# (just dependencies: pip install -r requirements.txt, then use `python -m charta.cli`)
# default local provider (required for AI; everything degrades gracefully without it)
ollama serve
ollama pull gemma4:e4b
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
python -m charta.cli doctor              # why won't it start? (read-only)
python -m charta.cli testmodel           # ask the model "hello" and print its reply
python -m charta.cli logs                # startup, errors and the exit reason
```

Right-click integration (Windows, no admin): `charta install-shell`
(Win11: entry under *Show more options*) — it opens the **setup window** for the
folder you clicked. `charta uninstall-shell` removes it.

**On Windows, start here:** `python -m charta.cli doctor` prints a read-only
readiness report (provider, icon, pywebview, DWM, shell entry, safety guard).
Then `python -m charta.cli testmodel` sends a one-word prompt end to end and shows
the model's reply with a PASS/FAIL status — the fastest way to prove the AI is
actually wired up. Full runbook and the visual checklist:
[`docs/WINDOWS.md`](docs/WINDOWS.md).

## Desktop app (Electron)

`desktop/` is a small Electron shell around the same local UI — no bundler, no
transpiler, the renderer is still the FastAPI HTML. It owns the native chrome:

- **Custom title bar** (`titleBarStyle: 'hidden'` + `titleBarOverlay`) that follows
  the in-app theme toggle, plus **Windows 11 Mica** (`backgroundMaterial`).
- **System tray**: close the window and Charta keeps watching; the tray menu opens
  the app, jumps to Review or Ask, or quits. One taskbar entry via AppUserModelID.
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

## What works now

- Charter create/load/edit + 3 presets (student, freelancer, data_entry)
- Extractors (txt/md/csv, PDF via PyMuPDF, docx) + **vision** for images and
  scanned PDFs (any vision-capable model; text is redacted before it is stored)
- Stable-file watcher, classification (model JSON or heuristic fallback) with human reasons
- **Suggest mode and auto mode** (`--mode auto`, opt-in per folder; `--dry-run` still moves nothing).
  Both modes go through one pipeline: protected-path refusal, journal + undo, collision suffix.
- Approve/reject, mover (dry-run, `(2)`-suffix collisions), journal + undo
- Receipts xlsx+csv, study notes+flashcards, data-entry table
- Gap detection, ask-with-citations (refuses to invent), sensitive-file guard
- Web UI (setup/overview/review/outputs/gaps/ask/activity/settings/styleguide), SSE live strip, voice hook (Web Speech in browser, faster-whisper in CLI)
- Native window with dark title bar, Mica + solid fallback, taskbar icon/grouping, tray, remembered geometry, custom dropdowns and folder picker (see *Native-feel polish*), plus the Electron desktop shell
- **Design system with tests**: WCAG-AA-checked palette (both themes), 4px spacing scale, 7-step type scale, and every `var(--token)` proven defined — `tests/test_design.py`
- **Measured UI checks**: `tools/ui_check.py` drives all 9 screens in both themes and fails on horizontal overflow, missing `h1`, targets under 24px, or console errors; it also writes `docs/screenshots/`
- **Diagnosable startup**: everything goes to `<state>/charta.log`, a session file records the running instance, and a busy port is recovered instead of aborting
- Protected folders are refused everywhere, including the web API (friendly full-screen page, HTTP 403 from `/api/charter`)

## What does NOT work yet

- Learned-rules-from-corrections, weekly digest, deadline timeline (M6 stretch, not started)
- Browser screenshots for README (no Playwright run in this env yet — `docs/screenshots/` pending)
- The native window (DWM dark title bar, Mica, .ico, taskbar grouping, remembered
  geometry) is **written but unverified**: it is implemented and unit-tested as a
  guarded no-op, but no one has run it on Windows yet. Browser fallback is what
  this machine exercises. `pywebview` is optional and not installed here.
- ElevenLabs STT (interface exists, clearly labeled cloud, off by default)
- Vision quality depends entirely on the model you point it at (4B local Gemma is
  rough on handwriting; a bigger or cloud vision model does much better)

## Why local and open

Your files never leave the device; the AI's memory is a Markdown file you own,
copy, and edit. Trade-offs, honestly: a 4B local model is slower and dumber than
cloud giants (heuristic fallback covers offline), vision/OCR is the bottleneck
(~seconds/page on iGPU). Ask uses keyword/BM25 ranking plus regex signals
(dates, months, amounts, document types) instead of embeddings, so there is no
second model to download and nothing to index ahead of time.
For a personal folder, that's the right trade.

## Performance (this machine, 2026-10-14)

- Heuristic classify: <0.1 ms/file; eval accuracy on 5 canonical samples: **5/5 (100%)**
- `pytest -q`: 107 passed in ~7s (includes a fake OpenAI-compatible server, so no provider is needed)
- `npm test` (shell helpers): 6 passed in ~0.15s; `npm run smoke`: 9 screens, no console errors
- `tools/ui_check.py`: 18 screens (9 routes × dark/light) measured + screenshotted in ~25 s
- `charta doctor`: read-only, <0.5 s, no writes to your folders
- Icon generation (`tools/make_icon.py`): 7 sizes, ~0.3 s, 19 KB — stdlib only
- LLM timings with a live provider: TBD — record `time charta watch` on your laptop and update STATUS.md

## Screenshots

`docs/screenshots/` holds every screen in both themes, generated (not hand-drawn)
by `tools/ui_check.py` and `npm run shots`. They double as the visual regression
baseline for the demo video.

## Layout

See `AGENTS.md` (rulebook), `STATUS.md` (progress log), `DESIGN.md` (design
system), `docs/WINDOWS.md` (Windows + desktop runbook), `desktop/` (Electron shell).
