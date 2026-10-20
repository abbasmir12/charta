# STATUS.md — Charta

> Public snapshot of the project state. How to run and test is at the bottom.

## Current Focus

Ship a demo that a stranger can reproduce in one command: `charta demo` builds
a messy folder, charters it, proposes and approves placements, and writes the
purpose output — offline, with no model or key required. The desktop app and
the watched-folder pipeline are built; the remaining work is the Windows visual
pass and a recorded before/after demo.

## What works

- [x] Folder Charter: create from text (or voice in the UI), edit, and three
      presets (student, freelancer, data entry). Stored as human-readable
      `.charta/charter.md` (Markdown + YAML front-matter).
- [x] Any OpenAI-compatible provider through one `LLMClient`: Ollama (default,
      local), LM Studio, llama.cpp, vLLM, OpenAI, OpenRouter, Groq, Together,
      DeepSeek, or a custom `base_url`. Keys come from env, never the repo.
- [x] Safe proposals: suggest mode by default, dry-run on every mutating
      command, protected-path refusal, collision suffixes, sensitive-content
      guard, and a journal so every move is undoable.
- [x] Purpose outputs: receipts spreadsheet (xlsx + csv), study notes +
      flashcards, and a data-entry table.
- [x] Gap detection (expected vs found) and "ask the folder" with file/page
      citations (keyword/BM25 + regex retrieval, no embeddings).
- [x] Real watching: a per-user watched-folders registry plus a background
      watcher hosted by the local backend; survives closing the window to the
      tray. Overview shows lane status, Scan now, and Stop watching.
- [x] Shell integration: right-click "Watch with Charta" in Explorer, a live
      tray menu, and per-folder "Being watched with Charta" verbs.
- [x] Local web UI (FastAPI + plain HTML/CSS/JS, no bundler, no CDN) and an
      Electron desktop shell with custom chrome, tray, and hardened defaults.
- [x] Voice input interface (`faster-whisper` locally) and vision for scanned
      PDFs/images through the same model client.
- [x] `charta demo`: deterministic messy folder + preset charter + propose +
      approve + purpose output in one command; offline by default, `--ai` to
      use the configured model, `--dry-run`, `--reset`, `--watch`.
- [x] 149 pytest tests, Electron unit tests, 27 measured UI screens.

## Done Log

- 2026-10-20: document that the `charta` command comes from installing the
  project (`pip install -e ".[native]"`), not from `pip install -r
  requirements.txt`. Files: `README.md`, `docs/WINDOWS.md`. Verified: docs only,
  `pytest -q` 162 passed.

- 2026-10-20: fix "charta open closes with nothing to show". Root cause: when the
  Electron binary is not downloaded (`desktop/node_modules/electron/dist/...`
  missing), `command()` fell back to `npx --no-install electron .`, which resolves
  slowly (~20 s) or fails and exits 0 — the launcher then reported "the window is
  up" without checking, and even its browser fallback pointed at a port where no
  backend was listening. Now: no Electron binary means no Electron (fall through
  to pywebview/browser with a printed `cd desktop && npm install` hint); the shell
  is told to spawn the launcher's own interpreter via `CHARTA_PYTHON`; on failure
  the launcher probes the port and starts its own backend on a fresh port before
  opening the browser; and it prints the shell/backend/app log paths instead of a
  false "window is up". Files: `charta/shell/electron.py`,
  `charta/shell/desktop.py`, `docs/WINDOWS.md`, `tests/test_electron.py`.
  Verified: `pytest -q` 162 passed.

- 2026-10-20: default generation model is now `gemma4:e4b` (what Ollama actually
  ships on this machine); config default, `config.toml` and the pull commands in
  README/WINDOWS/STATUS all updated. Files: `charta/core/config.py`,
  `config.toml`, `README.md`, `docs/WINDOWS.md`, `STATUS.md`. Verified: `pytest
  -q` 162 passed.

- 2026-10-20: add `charta testmodel` — a one-word end-to-end model check. It pings
  the provider, verifies the configured model is actually offered, sends `hello`
  through `/chat/completions`, and prints the reply plus a PASS/FAIL status
  (`--prompt`, `--timeout`, `--json`). Core function `doctor.test_model` returns a
  `ModelTest` report and never raises. Files: `charta/core/doctor.py`,
  `charta/cli.py`, `README.md`, `docs/WINDOWS.md`, `AGENTS.md`,
  `tests/test_openai_compat.py`, `tests/test_runtime.py`. Verified: `pytest -q`
  162 passed; live run shows PASS against a fake OpenAI endpoint and a clear
  FAIL+exit 1 when the provider is unreachable.

- 2026-10-20: remove embeddings completely; Ask is now lexical. `charta/core/ask.py`
  ranks chunks with BM25 keywords plus explainable signals: a per-file description
  (doc type, vendor, date, amount), filename matches, phrase/bigram matches,
  month/year/number/amount boosts, document-type intent, and a small domain
  synonym table; regexes extract dates, months and amounts. No `/embeddings`
  call, no embedding model, no numpy — the model is used only to write the final
  answer. Removed `embedding_model`, `CHARTA_EMBED_MODEL`, `[models] embedding`
  and the Settings row. Files: `charta/core/ask.py`, `charta/core/llm.py`,
  `charta/core/config.py`, `charta/web/app.py`, `config.toml`, `README.md`,
  `docs/WINDOWS.md`, `AGENTS.md`, `requirements.txt`, `pyproject.toml`, tests.
  Verified: `pytest -q` 157 passed; the demo folder answers "what did EDF charge
  in March?" with the EDF receipt and €87.40.
- 2026-10-20: doctor now checks the configured generation model against the provider's `/models` list, so an installed `gemma4:e4b` with `gemma4:e4b` configured is reported as a FAIL with the available ids instead of a healthy-looking ping. Generation 404s now name the missing model. Files: `charta/core/llm.py`, `charta/core/doctor.py`, `tests/test_openai_compat.py`, `tests/test_windows_paths.py`. Verified: `pytest -q` 156 passed.
- 2026-10-20: make model usage visible — `Proposal.origin` records `llm` vs
  `heuristic`, and `charta demo --ai` now prints how many files the model
  actually classified (or warns that it fell back). The demo also de-duplicates
  output paths and explains a missing `receipts.xlsx` when `openpyxl` is absent.
  Files: `charta/core/classify.py`, `charta/core/demo.py`, `charta/cli.py`,
  `tests/test_pipeline.py`, `tests/test_demo.py`. Verified: `pytest -q`
  152 passed; `--ai` against an unreachable provider prints the fallback warning.
- 2026-10-20: fix the launcher health check — `/api/health` is now liveness-only
  (about 40 ms) and never pings the model. Electron probes it with a 1.5 s
  timeout, so the old 2 s ping made a healthy server report "no response from
  /api/health" while it was starting fine. Files: `charta/web/app.py`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 150 passed; health returns 200
  in ~40 ms with the provider unreachable.
- 2026-10-20: initial public snapshot — folder charter, safe proposals and undo,
  purpose outputs, gaps, cited Q&A, real watching, tray/Explorer integration,
  Electron shell, and the one-command demo. Verified with `pytest -q`
  (149 passed), the UI measurement script (27 screens), and a headless Electron
  smoke run. Earlier development history is kept in a local archive branch.

## Next Up

1. Windows visual pass: Explorer menu, tray, Mica/title bar, close-to-tray.
2. Record a 60–90s before/after demo (`charta demo` → sorted folder + output).
3. Live-model pass on Gemma via Ollama for classification quality and vision.

## Blockers & Open Questions

- The Windows-only visuals (Explorer verb rendering, Mica, tray icon,
  close-to-tray) are written and unit-tested as guarded no-ops but have not
  been seen on a real Windows display yet.
- No live model on the Linux dev box: the provider path is verified against a
  local fake OpenAI-compatible server; real-model latency and vision quality
  are still to be measured.
- Fonts are not bundled; the UI uses the native system stack (no CDN).
- Open question: bundle pywebview by default, or keep it optional so the web UI
  works with zero extra installs?

## Decisions

- 2026-10-20: Retrieval is keyword/BM25 + regex, not embeddings. Why: it removes a
  second model and a vector store, works with every provider (including ones with
  no `/embeddings` route, e.g. OpenRouter chat-only), is deterministic and
  explainable, and for a personal folder the signals that matter — dates, months,
  amounts, document type, vendor, filename — can be extracted exactly with regex.
- One OpenAI-compatible client for every provider. "Bring your own model" must
  not mean editing client code; all supported services speak the same routes.
- Suggest mode is the default and the core never deletes. Every move goes
  through one pipeline (propose → approve → journal) so auto mode cannot be a
  second, laxer path.
- The watcher runs inside the local backend, not as a detached process: the
  Electron shell stays in the tray, so watching survives the window closing
  without PID files or a service.
- A per-user watched-folders registry, not the presence of `.charta`, is the
  source of truth; the tray, CLI, and UI must agree.
- A config-file `base_url` equal to a different provider's stock default is
  ignored, so `provider` alone selects the endpoint and a stale template value
  cannot silently call localhost.
- `charta demo --reset` only removes a folder carrying the demo marker; any
  other non-empty folder is refused, so the demo can never wipe real files.
- Explorer per-folder markers use the documented `AppliesTo` (AQS) verb instead
  of a native COM extension: reversible, HKCU-only, and testable without a
  Windows build; its rendering remains unverified.
- Structure before surface in the UI: hierarchy in grayscale first, one
  restrained accent for selection only, true-ink primary actions, and no
  card/pill soup. Design details live in `DESIGN.md`.

## Failures & Lessons

- A compound report ("terminal flashes, then 0 files tracked") had two causes:
  a console-script launcher and a UI that never actually watched. Split compound
  reports and verify each symptom.
- The headline feature was half-wired: a charter could be created, but nothing
  ever watched until the CLI was run. Trace the user's click all the way to the
  code that does the work.
- A pre-filled `base_url` in the shipped config outranked `provider`, so
  switching to OpenRouter still called localhost. Optional fields should ship
  blank; the selector should be the source of truth.
- Windows-specific branches pass on Linux only as guarded no-ops. Read the
  platform branch as if it were the only branch; do not confuse "the guard
  works" with "the feature works".
- A green UI check is necessary but not sufficient: reviewing rendered
  screenshots caught duplicated controls, cramped rows, and undersized hit
  targets that the assertions missed.

## How to Run & Test

```bash
git clone git@github.com:abbasmir12/charta.git
cd charta
pip install -r requirements.txt

python3 -m charta.cli demo                 # messy folder → sorted + receipts.csv (offline)
python3 -m charta.cli demo --preset student --reset
python3 -m charta.cli demo --ai            # use the configured model instead
python3 -m charta.cli open --folder ./charta-demo   # the desktop/browser UI

python3 -m pytest -q                       # 149 passed
python3 tools/ui_check.py                  # measured screens + docs/screenshots/
cd desktop && npm test && npm run smoke    # unit tests + 9 headless routes
cd desktop && npm start                    # Electron desktop app

python3 -m charta.cli doctor               # read-only readiness report
python3 -m charta.cli testmodel            # send 'hello' to the model, show reply + PASS/FAIL
python3 -m charta.cli logs                 # log tail + running session

# default local provider
ollama serve && ollama pull gemma4:e4b

# or any OpenAI-compatible endpoint (env wins over config.toml)
export CHARTA_BASE_URL=https://api.openai.com/v1 CHARTA_API_KEY=sk-... CHARTA_MODEL=gpt-4o-mini
```
