# Charta — your messy folder quietly sorts itself

Windows-first, local-first. Right-click any folder → **Watch with Charta** →
answer *"What is this folder for?"* (text or voice). A local Gemma model
(via Ollama) writes a **Folder Charter** (`.charta/charter.md`, human-editable),
and from then on the folder understands itself: proposes organization,
builds purpose-specific outputs, flags gaps, answers questions with citations.

**100% local:** all models run on your machine via Ollama. No cloud calls —
including UI assets (fonts/icons bundled, no CDN).

## Quickstart

```bash
pip install -r requirements.txt   # or pip install -e .
# start Ollama (required for AI; everything degrades gracefully without it)
ollama serve
ollama pull gemma3:4b
ollama pull nomic-embed-text

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
# 4. web UI
python -m charta.cli serve --port 8123   # → http://127.0.0.1:8123/overview?folder=./demo
```

Right-click integration (Windows, no admin): `charta install-shell`
(Win11: entry under *Show more options*). `charta uninstall-shell` removes it.

## What works now

- Charter create/load/edit + 3 presets (student, freelancer, data_entry)
- Extractors (txt/md/csv, PDF via PyMuPDF, docx, image stubs), stable-file watcher
- Classification (Gemma JSON or heuristic fallback) with human reasons
- Suggest-mode proposals, approve/reject, mover (dry-run, `(2)`-suffix collisions), journal + undo
- Receipts xlsx+csv, study notes+flashcards, data-entry table
- Gap detection, ask-with-citations (refuses to invent), sensitive-file guard
- Web UI (setup/overview/review/outputs/gaps/ask/activity/settings/styleguide), SSE live strip, voice hook (Web Speech in browser, faster-whisper in CLI)

## What does NOT work yet

- Vision OCR for scanned PDFs (stubbed as `vision-needed`; needs Gemma-vision wiring + RapidOCR fallback)
- Auto mode execution loop (charter stores `mode`, watcher still proposes; no auto-apply daemon yet)
- Learned-rules-from-corrections, weekly digest, deadline timeline (M6 stretch, not started)
- Browser screenshots for README (no Playwright run in this env yet — `docs/screenshots/` pending)
- Windows-only paths (DWM dark titlebar, Mica, .ico/AppUserModelID, custom folder picker) — stubbed/guarded; dev ran on Linux
- ElevenLabs STT (interface exists, clearly labeled cloud, off by default)

## Why local and open

Your files never leave the device; the AI's memory is a Markdown file you own,
copy, and edit. Trade-offs, honestly: a 4B local model is slower and dumber than
cloud giants (heuristic fallback covers offline), vision/OCR is the bottleneck
(~seconds/page on iGPU), and embeddings in SQLite won't scale past ~10k files.
For a personal folder, that's the right trade.

## Performance (this machine, 2026-10-13)

- Heuristic classify: <0.1 ms/file; eval accuracy on 5 canonical samples: **5/5 (100%)**
- `pytest -q`: 18 passed in ~0.5s; memory: negligible (<100MB, no models loaded)
- LLM timings with Ollama up: TBD — record `time charta watch` on your laptop and update STATUS.md

## Layout

See `AGENTS.md` (rulebook), `STATUS.md` (progress log), `DESIGN.md` (UI tokens).
