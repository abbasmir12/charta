# STATUS.md — Charta live progress log

> Protocol: see AGENTS.md §6. Update IMMEDIATELY after each task.
> Never batch, never start next task before STATUS reflects the last.
> One commit per task; hash goes in Done Log.

## Current Focus

AI layer is now provider-agnostic (OpenAI-compatible), vision + auto mode shipped
(42/42 green); next: verify against a *live* provider (Ollama or cloud) and on Windows.

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
  - [ ] M6.8 screenshots → docs/screenshots (+Playwright opt.)
  - [x] M6.9 shell install/uninstall + voice wiring
- [x] M7 Polish: sample-data generator, README (+screenshots/GIF, Why-local, perf), eval script + baseline, demo run-through.
- [x] M8 Any-provider AI: OpenAI-compatible `LLMClient` (Ollama / LM Studio / llama.cpp / vLLM / OpenAI / OpenRouter / Groq / Together / custom), env-var keys, vision for images + scanned PDFs, auto-mode apply loop behind one shared pipeline. Tests: fake OpenAI-compatible server + vision + pipeline.

## Done Log (newest first)

- 2026-10-14 08:55 UTC, STATUS record for M8 (this commit); files: STATUS.md; verified: `git log -1`; commit (this).
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

- Task: M6.8 screenshots + live-provider timing/quality (Ollama or a cloud model) on a real laptop.
- Plan: with a live endpoint, `time charta watch --scan` + record s/file and model tag; run the same on a scanned PDF to grade vision quality; screenshot each screen → docs/screenshots.
- Remains: screenshots, real-model numbers, DWM/Mica manual check on Windows.

## Next Up

1. Live-provider pass: JSON-validity rate + s/file for Ollama (gemma3:4b) and one cloud vision model on the scanned-PDF sample.
2. M6.8 Playwright/screenshot pass → docs/screenshots.
3. Windows verification: install-shell, %1/%V args, protected-folder refusal screen.

## Blockers & Open Questions

- No live provider on this box → the OpenAI-compatible path is verified against a local fake server (tests/conftest.py) plus a manual CLI/UI run; real-model timing and vision quality still TBD.
- Windows shell/DWM/.ico paths guarded but unverified — needs a Windows run.
- Fonts not yet bundled (Inter/JetBrains Mono pending) — CSS falls back to system fonts; no CDN used (good).
- Open question: should `provider` send an "OpenRouter-*" attribution header? Bot-blocking providers may want it; not needed for local use.

## Decisions

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

- 2026-10-14: Wrote a placeholder test that asserted nothing real (`img = fake_provider` reused as a path). Caught on read-back before `pytest` ran; rewritten to attach a real image and assert the data-URI part. Lesson: an assertion you can't explain is a bug, not coverage.
- 2026-10-14: Adding images to `build_index` initially indexed `[image file: x.png]` stub text when no vision model was configured. Fixed by skipping `image-stub` results. Lesson: widening an extractor's input set means revisiting what the *unavailable* path produces.
- 2026-10-13: Wrote `open(flash_path, ".feed" if False else flash_path, ...)` — nonsense mode arg in build_study (leftover edit). Caught on read-through before tests ran; fixed to plain `"w"`. Lesson: re-read new files before testing; 18/18 after fix.
- 2026-10-13: `pip install` blocked by PEP 668 (externally-managed env); fixed with `--break-system-packages`. Lesson: check env first on Kali.
- 2026-10-13: Assumed pytest present; it wasn't. Lesson: verify test runner in M0 before writing tests.

## How to Run & Test

```bash
cd /home/kali/projects/charta
python3 -m pytest -q                       # 42 passed
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
```
