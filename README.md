# Charta

**Your folders, finally intelligent.**

Right-click any folder in Windows, choose **Watch with Charta**, tell it in one
sentence what the folder is for, and from that moment the folder understands
itself. Drop anything into it, such as invoices, lecture slides, scans or
receipts, and Charta reads each file once, renames it, moves it into the right
subfolder and indexes what is inside. Then you just ask. *"How much did I spend
since January?"* gets a plain answer with the exact file and page it came from.

<a href="https://youtu.be/Y1YP2tSMvu4"><img src="https://img.youtube.com/vi/Y1YP2tSMvu4/maxresdefault.jpg" alt="Charta demo — drop invoices into a watched folder and watch it file itself" width="720"></a>

▶ **[Watch the 90-second demo](https://youtu.be/Y1YP2tSMvu4)**

Everything runs locally by default with a local Gemma model through Ollama, and
because the client speaks the standard OpenAI-compatible API the same code works
with LM Studio, llama.cpp, vLLM, OpenAI, OpenRouter, Groq, Together or DeepSeek
by editing one config file. No cloud calls unless you point it at one, no
telemetry, and no CDN (fonts and icons are bundled).

---

## How it works

1. **You name the folder's purpose.** One sentence, typed or spoken: *"freelance
   invoices and receipts for my taxes"*. It becomes a **Folder Charter** at
   `.charta/charter.md`, a Markdown file with YAML front-matter that you can open
   in Notepad and edit by hand. This file is the AI's memory, and you own it.
2. **Everything that lands in the folder is read once.** A stable-file watcher
   waits until the copy finishes, then extracts the text (PDF via PyMuPDF,
   DOCX/XLSX/CSV/TXT, images and scans through a vision model), classifies it
   with a short human reason, and proposes a home: `Invoices/2026/`,
   `Lectures/`, `Insurance/`.
3. **It gets indexed, not re-read.** `.charta/index.db` (SQLite, one file, no
   vector database) gets a row per file: path, description, document type, tags,
   dates, vendor, amounts and the text of the pages. Asking a question reads
   these rows plus BM25 keyword ranking and regex signals for dates, months and
   amounts, so answers come in milliseconds instead of re-opening your files.
4. **Nothing moves without you.** Suggest mode is the default: you get a list of
   proposed changes with reasons. Approve them and every move is journaled in
   `.charta/journal.jsonl` and committed to a private git history inside the
   folder, so one click or `charta undo` puts a file back.
5. **Ask the folder.** The model gets a catalogue of the index and three tools
   (`search_index`, `read_file`, `list_files`) and answers with citations from
   what it actually found. When the folder has nothing relevant, it says so
   instead of inventing an answer.

## Features

- **Folder Charter** created from text or voice, with presets for a student's
  lectures, a freelancer's receipts and invoices, and data-entry folders.
- **Automatic organization** you approve: proposed moves with a plain-language
  reason for each one, dry-run preview, collision-safe renames, undo for
  everything.
- **A searchable index per folder**, including screenshots and photos read
  through your model's vision, plus a **Search** page across names, tags,
  descriptions and content.
- **Ask with tools and citations**: a real agent loop where the model calls
  `search_index`, `read_file` and `list_files` itself, every step shown live in
  the UI, with a persistent chat per folder so follow-up questions work.
- **Purpose-built outputs**: a receipts spreadsheet (`.xlsx` + `.csv`), study
  notes with flashcards (`.md` + `.csv`), or a data-entry table, generated from
  the folder's actual files.
- **Gap detection**: *"no electricity bill for March"*, *"lecture 7 is missing"*.
- **A sensitive-file guard**: ID numbers, card numbers, IBANs and passwords are
  detected and kept out of the search index by default, and the file is marked
  sensitive in the proposals.
- **History you can trust**: an editable reader for every file, edits that keep
  the old version, a reversible trash, and a private git history recording every
  index, move and edit with a readable message.
- **Voice**: push-to-talk on `Ctrl+Space`, local transcription with Moonshine or
  faster-whisper by default, and ElevenLabs as an opt-in cloud option that is
  clearly labelled as cloud.
- **A desktop app feel**: native window with a custom title bar and system tray,
  Explorer right-click integration, and live background watching that survives
  closing the window.
- **Optional observability**: point a Sentry DSN at `[observability]` and every
  ask becomes a `gen_ai.invoke_agent` trace with model and tool spans, token
  counts and latency. Without a DSN it is a silent no-op and nothing leaves the
  machine.

## Quickstart

Requirements: **Python 3.11+** on Windows 10/11 (the core stays cross-platform
and passes on Linux CI). For the AI parts you need Ollama, or any
OpenAI-compatible endpoint. Node is only needed for the Electron desktop shell.

```bash
pip install -e ".[native]"        # installs the `charta` command + native window

# default local provider (everything still degrades gracefully without it)
ollama serve
ollama pull gemma4:e4b            # or whatever [models] generation names

charta open .                     # opens the UI for this folder
```

Then, either from the UI or the CLI:

```bash
# 1. create a charter
charta charter --folder ./demo --text "receipts and invoices I track for freelance taxes"

# 2. scan + propose (suggest mode: nothing moves until you approve)
charta watch ./demo --scan --once
charta proposals --folder ./demo
charta approve --folder ./demo --all --dry-run   # preview
charta approve --folder ./demo --all             # move + journal
charta undo --folder ./demo                      # undo one move

# 3. gaps + questions + outputs
charta gaps --folder ./demo
charta ask --folder ./demo "what electricity bills for March?"

# 4. daily use
charta watchd          # background watcher for every watched folder
charta doctor          # read-only readiness report
charta testmodel       # prove the model is wired up end to end
charta logs            # startup, errors and the exit reason
charta stop            # close the running instance cleanly
```

On Windows, `charta install-shell` adds the right-click **Watch with Charta**
entry to Explorer (no admin needed; on Windows 11 it lives under *Show more
options*), and `charta uninstall-shell` removes it again.

## Try it in 30 seconds, no model needed

The built-in demo runs entirely on offline heuristics, so it works before you
have configured any provider:

```bash
pip install -r requirements.txt
python -m charta.cli demo                         # builds ./charta-demo, sorts it, writes receipts.csv
python -m charta.cli open --folder ./charta-demo  # same folder in the UI
```

It writes 8 realistic files, creates a freelancer charter, proposes placements,
approves them and produces `.charta/outputs/receipts.csv` (plus `.xlsx` when
`openpyxl` is installed). Add `--ai` to let your configured model do the
classifying, `--preset student|data_entry` for the other outputs, `--watch` to
leave the folder watched, `--dry-run` to see proposals without moving anything,
and `--reset` to rebuild.

There is also a messier, hand-built sample at `samples/flat-paperwork/`: 27
files flat at the root, including EDF bills with March deliberately missing, an
insurance attestation, a bank CSV, photos, a letter and one sensitive residence
permit. It is made for trying the watcher and the sensitive-file path.

## Configuration

One config file, and it is yours. `config.toml` is git-ignored because it
belongs to the machine, so a `git pull` can never undo your edit. A fresh clone
ships `config.toml.example`; copy it once and Charta finds it (search order:
the `CHARTA_CONFIG` env var, the package directory, the state dir, the cwd).

> The **Settings page** in the UI edits all of this and writes it straight to
> your `config.toml`, and `charta doctor` prints which file is in use.

The `[llm]` section selects the provider, and `provider` alone is usually
enough: leave `base_url` blank and the endpoint in the table below is used.

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

Keys stay out of the repo. Use env vars instead of the `api_key` field:
`CHARTA_API_KEY` (also picks up `OPENAI_API_KEY` for cloud providers),
`CHARTA_BASE_URL`, `CHARTA_MODEL`. For a quick cloud setup without Ollama:

```bash
export CHARTA_BASE_URL=https://api.openai.com/v1 CHARTA_API_KEY=sk-... CHARTA_MODEL=gpt-4o-mini
```

If the endpoint is unreachable, Charta never crashes: every call has a timeout
and one retry, then it falls back to heuristics and tells you which provider and
URL failed.

## Safety by default

- **Suggest mode** is the default; auto mode is opt-in per folder, and
  `--dry-run` still moves nothing.
- **Never deletes.** Files are moved or copied; "Move to trash" in the UI is a
  move into `.charta/trash/`, which is reversible.
- **Undo everything.** `.charta/journal.jsonl` plus a private git history means
  a wrong move is one click or `charta undo` away.
- **Protected paths are refused** (Windows, Program Files, AppData, drive roots,
  your profile root), including through the web API, with a friendly full-screen
  page instead of an error dump.
- **Sensitive content stays out of the index** by default, and every AI decision
  carries a reason in plain language: *"Invoices/2026 — electricity bill from
  EDF dated March 2026."*

## The desktop app (Electron)

`desktop/` is a small Electron shell around the same local UI. There is no
bundler and no transpiler; the renderer is still the FastAPI HTML, and the UI
keeps working in a plain browser without it. The shell adds:

- a custom title bar that follows the in-app theme, plus Windows 11 Mica;
- a **system tray**: closing the window keeps Charta watching, with tray menu
  entries to open the app, jump to Review or Ask, or quit;
- **push-to-talk** on `Ctrl+Space` that works globally, even from the tray;
- hardened defaults per Electron's security checklist: `contextIsolation`,
  `sandbox`, `nodeIntegration: false`, navigation limited to local URLs.

```bat
cd desktop
npm install
npm start            :: run the app
npm run debug        :: keep browser keys + DevTools for development
npm test             :: unit-test the shell helpers (no display needed)
```

The shell never touches your files: it starts `charta serve` on a free port,
waits for `/api/health`, and everything else goes through the same guarded core.

## Project layout

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
tests/       pytest suite
```

## Docs

- [`STATUS.md`](STATUS.md) — what works, what is next, decisions and failures
- [`DESIGN.md`](DESIGN.md) — the design system the UI follows
- [`docs/WINDOWS.md`](docs/WINDOWS.md) — Windows and desktop runbook
- [`AGENTS.md`](AGENTS.md) — the rulebook for AI agents working on this repo
  (safety rules, config rules, tests)
