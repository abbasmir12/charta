# Charta — your messy folder quietly sorts itself

Windows-first, local-first. Right-click any folder → **Watch with Charta** →
answer *"What is this folder for?"* (text or voice). A local Gemma model
writes a **Folder Charter** (`.charta/charter.md`, human-editable), and from
then on the folder understands itself: proposes organization, builds
purpose-specific outputs, flags gaps, answers questions with citations.

**Local by default:** all models run on your machine. No cloud calls —
including UI assets (fonts/icons bundled, no CDN).

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

```toml
[llm]
provider = "openai"
generation_model = "gpt-4o-mini"     # [models] section
```

Keys stay out of the repo — use env vars instead of the `api_key` field:
`CHARTA_API_KEY` (also picks up `OPENAI_API_KEY` for cloud providers),
`CHARTA_BASE_URL`, `CHARTA_MODEL`, `CHARTA_EMBED_MODEL`.

If the endpoint is unreachable Charta never crashes: it falls back to
heuristics and tells you which provider and URL failed.

## Quickstart

```bash
pip install -r requirements.txt   # or pip install -e .
# default local provider (required for AI; everything degrades gracefully without it)
ollama serve
ollama pull gemma3:4b
ollama pull nomic-embed-text
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
# 4. UI — native window (pywebview) or your browser
python -m charta.cli open ./demo         # opens the setup window for that folder
python -m charta.cli serve --port 8123   # → http://127.0.0.1:8123/overview?folder=./demo
```

Right-click integration (Windows, no admin): `charta install-shell`
(Win11: entry under *Show more options*) — it opens the **setup window** for the
folder you clicked. `charta uninstall-shell` removes it.

**On Windows, start here:** `python -m charta.cli doctor` prints a read-only
readiness report (provider, icon, pywebview, DWM, shell entry, safety guard).
Full runbook and the visual checklist: [`docs/WINDOWS.md`](docs/WINDOWS.md).

## Native-feel polish

`charta open` is meant to feel like an app, not a tab:

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
- Native window with dark title bar, Mica + solid fallback, taskbar icon/grouping, remembered geometry, custom dropdowns and folder picker (see *Native-feel polish*)
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
(~seconds/page on iGPU), and embeddings in SQLite won't scale past ~10k files.
For a personal folder, that's the right trade.

## Performance (this machine, 2026-10-14)

- Heuristic classify: <0.1 ms/file; eval accuracy on 5 canonical samples: **5/5 (100%)**
- `pytest -q`: 66 passed in ~7s (includes a fake OpenAI-compatible server, so no provider is needed)
- `charta doctor`: read-only, <0.5 s, no writes to your folders
- Icon generation (`tools/make_icon.py`): 7 sizes, ~0.3 s, 19 KB — stdlib only
- LLM timings with a live provider: TBD — record `time charta watch` on your laptop and update STATUS.md

## Layout

See `AGENTS.md` (rulebook), `STATUS.md` (progress log), `DESIGN.md` (UI tokens).
