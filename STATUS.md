# STATUS.md — Charta live progress log

> Protocol: see AGENTS.md §6. Update IMMEDIATELY after each task.
> Never batch, never start next task before STATUS reflects the last.
> One commit per task; hash goes in Done Log.

## Current Focus

STEP 0 bootstrap: AGENTS.md + STATUS.md + DESIGN.md created, committing.

## Milestones

- [ ] M0 Scaffold: repo, AGENTS.md, STATUS.md, config, CLI skeleton, Ollama check, one passing test.
- [ ] M1 Charter: create from text via Gemma, charter.md w/ YAML front-matter, load/edit, 3 presets. Extractors (PDF/images/txt/docx). Stable-file watcher.
- [ ] M2 Classification & proposals: Gemma propose dest+name+reason; list/approve/reject; mover; undo journal; dry-run; collision suffix; protected-path refusal. Safety-rule tests.
- [ ] M3 Purpose outputs: receipts xlsx+csv; study notes+flashcards; data-entry table; auto-update on approve.
- [ ] M4 Gap detection: expected-vs-found report; UI + CLI.
- [ ] M5 Ask the folder: chunk/embed/retrieve; cited answers; refuse-to-invent.
- [ ] M6 UI, voice, shell:
  - [ ] M6.1 tokens.css, fonts, icons, /styleguide
  - [ ] M6.2 app shell (sidebar, topbar, palette, theme)
  - [ ] M6.3 setup window w/ voice + charter cards
  - [ ] M6.4 Review screen w/ keyboard + fly animation
  - [ ] M6.5 Outputs, Gaps, Ask (+drawer), Activity, Settings
  - [ ] M6.6 empty/loading/error/Ollama-offline states
  - [ ] M6.7 a11y + reduced-motion pass
  - [ ] M6.8 screenshots → docs/screenshots (+Playwright opt.)
  - [ ] M6.9 shell install/uninstall + voice wiring
- [ ] M7 Polish: sample-data generator, README (+screenshots/GIF, Why-local, perf), eval script + baseline, demo run-through.

## Done Log (newest first)

(none yet — STEP 0 commit lands next)

## In Progress

- Task: STEP 0 — root files + first commit.
- Plan: write AGENTS.md, STATUS.md, DESIGN.md → `git init`, commit.
- Remains: run init+commit, record hash, flip Current Focus to M0.

## Next Up

1. M0 scaffold (config.toml, charta pkg, CLI, Ollama ping, pytest green).
2. M1 charter + extractors + watcher.
3. M2 proposals/mover/journal/safety tests.

## Blockers & Open Questions

- None. Assumption: Linux dev box now, Windows target for shell/DWM polish (guard w/ platform checks).

## Decisions

- 2026-10-13: Stack = FastAPI+vanilla JS, SQLite+blobs, watchdog, PyMuPDF, openpyxl, faster-whisper, Ollama Gemma-4B-class + embedding model configurable. Why: prompt-mandated, laptop-friendly, no external services.
- 2026-10-13: Suggest-mode default, journal+undo, dry-run, no-delete enforced in core (not just UI). Why: safety rules non-negotiable + demo trust story.
- 2026-10-13: Fonts/icons bundled locally, no CDN. Why: "100% local" claim must be true including UI assets.

## Failures & Lessons

(none yet)

## How to Run & Test

```bash
cd /home/kali/projects/charta
python -m pytest -q          # once scaffold lands
python -m charta.cli --help  # once CLI lands
```
