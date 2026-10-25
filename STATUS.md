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
- [x] Voice input interface (faster-whisper locally by default; Moonshine,
      system speech, or cloud ElevenLabs selectable in Settings) and vision
      for scanned PDFs/images through the same model client.
- [x] The Settings page is editable — provider, base URL, key, models,
      voice provider — saved straight into machine-local config.toml.
- [x] Push-to-talk voice: Ctrl+Space (global in the Electron shell, even from
      the tray) records, transcribes, and asks; an answer-ready
      notification fires when the window is hidden.

- [x] 274 pytest tests, Electron unit tests, 36 measured UI screens.
- [x] `charta demo`: deterministic messy folder + preset charter + propose +
      approve + purpose output in one command; offline by default, `--ai` to
      use the configured model, `--dry-run`, `--reset`, `--watch`.

## Done Log

- 2026-10-25: **the voice wave, properly this time: push-to-talk popup,
  real STT providers, and a full Settings UI that writes config.toml.**
  The last wave shipped a popup that called `window.__recordAudio` — a
  function that never existed — and a fake ElevenLabs endpoint; both are
  gone. Now: `charta/voice/stt.py` is a real provider dispatcher (local
  Whisper, Moonshine ONNX with webm→16 kHz PCM conversion via PyAV,
  system/SpeechRecognition, and a real ElevenLabs multipart upload with
  friendly HTTP errors); `POST /api/voice` takes raw audio bytes and uses
  the configured provider (client never handles keys); `GET/POST
  /api/settings` read/write `[llm]`/`[models]`/`[voice]` in config.toml
  (atomic write + `.toml.bak`, `null` clears a key, `""` keeps it, stale
  stock base URLs drop on provider switch) and the Settings page is an
  editable form with a save bar. Ctrl+Space is push-to-talk in the browser
  (hold=record, release=transcribe) and a global toggle in Electron
  (works from the tray); the bottom voice popup is token-styled CSS with a
  pulsing orb; transcripts land in the Ask composer and auto-send; when an
  answer completes, a toast / native notification fires if the window is
  hidden or the question was asked by voice. Answers got an entrance
  animation, depth, sticky table headers and styled quotes. New tests:
  `tests/test_stt.py` (15), `tests/test_settings_voice.py` (8).
  Files: `charta/voice/stt.py`, `charta/core/config.py`,
  `charta/web/app.py`, `charta/web/static/app.{js,css}`,
  `desktop/main.js`, `desktop/preload.js`, `tests/`, `DESIGN.md`.
  Verified: `pytest -q` 274 passed; `node --check` on all JS;
  `tools/ui_check.py` pending below. Commit: see next line.

- 2026-10-24: **conversation titles now come from the AI on first exchange;
  rail meta rewritten; "+ New" button replaces the text chip.** At the end of
  the first exchange (answer recorded), `_run_ask` asks the model for a
  2–6 word title via strict-JSON `chat()` (client retries internally),
  falling back to the question's first line when the provider is down — the
  naming runs before the job's `done` event so the rail is fresh. Item meta
  became "N messages, <age>" via `chats.meta_line` / `chats.rel_time`
  (server) and a mirrored JS `relTime`. The text "New" chip became a quiet
  circular `.plusbtn` (+) button. Tests: chats title/fallback/meta suites
  updated. Files: `charta/core/chats.py`, `charta/web/app.py`,
  `charta/web/static/app.js`, `tests/test_chats.py`, `DESIGN.md`.
  Verified: `pytest -q` 248 passed; `tools/ui_check.py` 36 screens clean.
  Commit: d18bc6c.

- 2026-10-24: **conversations moved into the main rail as a collapsible
  subtree under Ask** and the in-page conversations column removed. The
  Work rail now shows "Conversations — [chips New]" under Ask on every
  screen that has a folder: one tree item per saved chat (title, message
  count, newest first), the tree opens automatically once chats exist,
  and clicking an item opens it on the Ask page (the anchor href
  /ask?folder=..&chat=.. degrades without JS; with JS the click is
  intercepted so the chat opens without a reload, and the tree expands).
  A question in a new chat refreshes the tree in place; the active
  conversation gets the rail's accent edge, matching the active-page row.
  New-chat measurement caught one CSS specificity trap: ".sidebar a" beat
  ".conv-item" and re-imposed the row layout — items are now styled as
  ".sidebar .conv-item" explicitly, and the crowding that clipped the New
  chip was fixed by dropping the count chip (details + summary is the
  accordion, no custom JS needed). Files: `charta/web/app.py`,
  `charta/web/static/app.js`, `app.css`, `tests/test_web_ui.py`,
  `DESIGN.md`. Verified: `pytest -q` 246 passed; `tools/ui_check.py`
  36 screens clean; seeded two-conversation screenshot checked in light. Commit: d18bc6c.- 2026-10-24: **the Ask page rebuilt around a modern chat layout** (from the
  user's reference: chat-history sidebar, centred prompt, starter cards).
  The page is now a full-height app layout: a conversations rail (this
  folder's saved chats, newest first; below 1100px it folds away) beside a
  chat pane. Empty state: a centred greeting above the large rounded composer
  (autogrow textarea, mic button, model chip, solid round send button,
  Enter asks / Shift+Enter makes a line) with four starter cards underneath —
  folder inventory, newest files, the charter's expected items, and missing
  items. Once the conversation starts the greeting disappears, the log
  scrolls and the composer pins to the bottom, exactly like the reference.
  Replayed conversations now render their stored source chips too, and the
  citation chips are shared by live answers and replays (citesHtml). One
  bug found by browser measurement: the pane toggle used class "live",
  which the toolbar already styles with max-width:34ch — the whole pane
  collapsed to 260px once a conversation started; renamed to "chatting".
  Files: `charta/web/app.py`, `charta/web/static/app.js`, `app.css`,
  `tests/test_web_ui.py`, `DESIGN.md` (Ask spec refreshed).
  Verified: `pytest -q` 246 passed; `tools/ui_check.py` 36 screens clean
  (no overflow, no small targets, no console errors); simulated live
  conversation screenshotted correct in light and dark. Commit: 36535cd.- 2026-10-24: **Ask conversations persist, and follow-ups remember what was
  asked before.** Each Ask-page conversation is a user-owned file,
  `.charta/chats/<id>.json` (id, created, title = first question's first
  72 characters, one message per exchange with q/answer/blocks/model/
  citations/at) — `charta/core/chats.py`. `/api/ask` now speaks a chat
  protocol: `chat:"new"` starts a conversation, `chat:"<id>"` continues
  one (unknown ids fall back to fresh), `chat:""` stays ephemeral so the
  dashboard ask boxes create nothing. `_run_ask` sends the earlier turns
  to the model via `ask_with_tools(..., history=...)` (user/assistant
  pairs, last 6 turns, each capped at 1600 characters — history is a
  brief, not a dump) and records every answered turn (agent path, fallback
  path, and the empty-index path). Two read APIs back the UI: `/api/chats`
  (newest first) and `/api/chat` (full transcript, 404 when gone). The Ask
  page shows an "Earlier conversations" strip of repeatable cards; clicking
  one replays the whole transcript and continues it; askOnce now carries
  the conversation id and the work block says "Continuing the conversation
  (N earlier turn(s))". Sources became proper chips (file icon, basename,
  page badge); clicking opens the file in its default app and falls back to
  revealing it — paths are normalised to `/` and strawberries like `'` are
  encoded as `%27` because encodeURIComponent leaves quoting marks alone;
  chips no longer build inline JS strings with nested quotes — onclick
  handlers read `this.dataset`, which cannot break parsing. The "Tools the
  model can call" section left the Ask page. Files: `charta/core/chats.py`,
  `charta/core/agent.py`, `charta/web/app.py`, `app.js`, `app.css`,
  `tests/test_chats.py`, `tests/test_web_ui.py`. Verified: `pytest -q`
  246 passed (10 new), `node --check` on app.js. Commit: 8b124b0.

- 2026-10-23: **approved files no longer return to Review after a restart,
  and approving an already-placed file cannot create "name (2)" anymore.**
  The restart-scan called process_new_file for every file, and
  proposals.upsert replaced the approved proposal with a fresh pending one
  (same file back in Review); approving that duplicate found the target
  occupied by the file itself, so the collision rule suffixed it (2).
  Three fixes: upsert never resurrects a decided (approved/rejected)
  proposal; the pipeline skips proposing files already at a decided
  proposal's source OR destination path (organized_paths), so renamed or
  moved approvals are recognised under their new name; and the mover treats
  a self-move as a no-op ("already at its place") instead of a collision.
  Files: `charta/core/proposals.py`, `pipeline.py`, `mover.py`,
  `tests/test_safety.py`. Verified: `pytest -q` 236 passed, including a
  replay of the exact restart-then-approve sequence.


- 2026-10-23: **Review approve now feels final in the UI.** Approving used
  to post the request, dim the *first* card (not the one you acted on) and
  show a toast — the card stayed, unlike Reject which reloaded. Each card
  now carries its proposal (`data-src`); approving targets that card,
  animates it out (opacity + slide), updates the selection and the
  "N left in review" toast, and when the queue empties reloads into the
  "All clear" state. Tests lock in the data-src wiring and the removal
  behaviour. Files: `charta/web/app.py`, `app.js`, `app.css`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 233 passed.


- 2026-10-23: **off-protocol answers no longer dump raw markdown** (user
  screenshot showed '###' mid-line and a pasted form dump rendered as one
  giant paragraph). The fallback path is now a real markdown→blocks
  converter (`_markdown_to_blocks`): '#'-headings, bold-only section lines,
  '-' lists, '|' tables and paragraphs all become the same typed blocks the
  protocol produces, and stray mid-line hash runs ('document: ### Visible
  text') are scrubbed. The agent also retries once when the model ignored
  the protocol (not only when it sent broken JSON), and the system prompt
  now forbids '###' anywhere and pasting long raw text — summarise instead.
  Files: `charta/core/agent.py`, `tests/test_agent.py`. Verified:
  `pytest -q` 232 passed; the exact screenshot content converted to
  p/heading/list/table/heading/p with zero hashes.


- 2026-10-23: **answers now follow a strict JSON blocks protocol.** The
  model's final answer must be `FINAL: {"blocks":[...]}` with typed blocks
  only (heading 1–3 / p / list / table / facts), validated with Pydantic in
  `agent.py` (`structured_answer`); markdown artifacts (`###`, `**`, pipes)
  are stripped from block text server-side, so they can never reach the
  answer. The UI (`renderBlocks`) renders typed blocks directly instead of
  parsing model markdown, and the md() renderer remains only as fallback.
  De-protocol answers degrade to clean plain-paragraph blocks (never raw
  markdown), one corrective retry when the model tries JSON but misses, and
  the double-parse bug (agent flattened the answer, then _run_ask re-parsed
  the flattened text) was fixed by keeping `AgentResult.raw`. RENAME/MOVE/
  GAP lines after the FINAL line still become proposals and AI gaps.
  Files: `charta/core/agent.py`, `charta/web/app.py`, `app.js`, `app.css`,
  `tests/test_agent.py`, `tests/test_web_ui.py`. Verified: `pytest -q`
  231 passed; end-to-end run with a scripted model produced heading/facts/
  p/table/list blocks with zero hashes.


- 2026-10-23: **`###` now renders as a real headline.** Two causes: the
  heading regex required a space after the hashes (`###Title` fell through
  and showed literally), and matched `###` mapped to `h5`, which had no CSS
  — so it looked like plain small text. The renderer now takes 1–6 hashes
  with an optional space, maps `#`/`##` → h3 (subtitle-size headline),
  `###` → h4 (body-size with a rule underneath), `####`+ → h5 (small caps),
  and treats a fully bolded line as a heading (models do that). A pytest
  executes md() via node when available and asserts hashes never leak into
  the rendered HTML. Files: `charta/web/static/app.js`, `app.css`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 227 passed; node run of
  md() over mixed headings.


- 2026-10-23: **the ask experience rebuilt around how modern AI apps behave**
  (researched: Perplexity/Claude-style streaming work, in-place accordions,
  markdown answers). The question now streams its work over Server-Sent
  Events (`/api/ask/stream`): each tool call appears inside the chat the
  moment it happens in a collapsible work block ("thinking… → searched ·
  read → ✓ 6 steps of work"), instead of a top-section timeline appearing all
  at once. Answers render as **Markdown** through a small local renderer
  (bold, headings, lists, tables, code — escaped first, no CDN) with
  highlighted dates and amounts, and clickable `[file pN]` citation chips
  that open the file. The yellow top banner is gone (a quiet reload chip
  replaces it). Revision+start time on the ask footer (`.askbuild` chip).
  Files: `charta/web/app.py`, `app.js`, `app.css`, `tests/test_web_ui.py`.
  Verified: `pytest -q` 225 passed; SSE end-to-end with a scripted model.

- 2026-10-23: **the AI can now propose organisation, and gaps come only
  from it.** The agent may end its answer with RENAME / MOVE / GAP lines:
  renames+moves become Review proposals (origin "llm", still nothing moves
  without approval) and gaps are stored in `.charta/ai_gaps.json` shown on
  the gaps page ("only it proposes these"). The automated expectations scan
  and its counts/buttons were removed from overview and dashboard; "Missing
  items" now counts model-noticed gaps. Files: `charta/core/agent.py`,
  `charta/web/app.py`, `tests/test_agent.py`, `tests/test_web_ui.py`.
  Verified: `pytest -q` 225 passed; end-to-end run produced one pending
  rename proposal + one AI gap file.

- 2026-10-23: **the outputs page rebuilt.** Four honest cards (what it is,
  item count, file paths, when it was built) with an inline preview table
  (first 8 rows; xlsx path shown), and Show file / Rebuild / Hide preview
  per card — replacing the confusing tab+JSON grid. Files:
  `charta/web/app.py`, `app.js`, `app.css`, `tests/test_runtime.py`.
  Verified: `pytest -q` 225 passed.

- 2026-10-21: **charta stop now kills the whole family.** The user restarted
  Charta ~100 times and kept seeing the stale UI, because Electron spawns its
  own Python backend; stopping only the recorded (shell) pid orphans the
  Python child, which keeps serving the window old code forever. `charta
  stop` now kills the recorded pid's tree (taskkill /T), sweeps every port
  Charta ever recorded (or configured) for orphans still listening — and
  only ever kills a listener whose command line says charta. Each window
  also prints which git revision and backend start time it is running from
  (bottom of the Ask page, plus /api/version), so a stale window is visible
  at a glance. Files: `charta/cli.py`, `charta/web/app.py`,
  `tests/test_cli_stop.py`. Verified: `pytest -q` 221 passed; orphan sweep
  tested against a real listener and a foreign listener left untouched.

- 2026-10-21: **the server now forbids caching itself.** A stale app.js in
  the window was the recurring suspect for phantom failures, so every page
  and static file is now served with `Cache-Control: no-store` — Electron
  keeps windows open for days while the app gets updated underneath them,
  and a cached script against a changed API looks like a broken feature.
  Files: `charta/web/app.py`, `tests/test_web_ui.py`. Verified: `pytest -q`
  219 passed.

- 2026-10-21: **"not found" answers became useful, and blind image reads
  stopped.** The user's log showed Ask working end to end (the model calls
  list_files and read_file; the job finishes done) — but (a) a question like
  "hi" that matches nothing returned a bare dead end, and (b) the agent read
  screenshot PNGs and got nothing back, then still went on. Now a no-match
  answer lists what the folder DOES contain (up to 8 file names) and points
  at them, and read_file on an unindexed path explains that there is no text
  and to use search_index or the catalogue instead. Files: `charta/core/
  ask.py`, `charta/core/agent.py`, `tests/test_agent.py`,
  `tests/test_features.py`. Verified: `pytest -q` 218 passed; the user's own
  `charta logs` showed the tool loop completing on their Windows machine.

- 2026-10-21: **THE "instant No answer" bug, actually found.** The per-folder
  ask box on the Folders dashboard (`askIn` in app.js) still read the Ask API
  synchronously after Ask became a job API: it got a job object, found no
  `answer` field, and rendered "No answer." immediately — without ever
  calling the model. Fully valid restarts looked broken; three earlier fixes
  missed it because they only covered the Ask page. Now `askIn` polls the
  job like the Ask page (inline steps, "I stopped: <reason>" on failure, a
  plain "No answer came back" only when the job itself is empty), and a
  regression test walks every ask function in app.js and requires them to
  poll the job and never read `j.answer` raw. Files:
  `charta/web/static/app.js`, `tests/test_web_ui.py`. Verified: `pytest -q`
  216 passed; `node --check` on app.js.

- 2026-10-21: **diagnosing a broken answer got one-click easy.** An Ask job
  that fails now says so in the chat ("I stopped: <reason> … Last step: …")
  instead of vanishing into a toast, every ask job is logged to the app log
  (`charta logs` shows every step even if the window is the problem), the Ask
  page has a **Copy diagnostics** button (page build vs server build, the
  last job's full status), and a new `charta stop` closes the running
  instance cleanly — it clears a stale session but never touches an
  unrelated process. Files: `charta/web/static/app.js`, `charta/web/app.py`,
  `charta/cli.py`, `tests/test_cli_stop.py`. Verified: `pytest -q` 215
  passed; stop tested against a live listener and a stale session.

- 2026-10-21: **a stale window now says so.** A window opened before an
  update keeps running yesterday's JavaScript against today's API — the Ask
  answer arrives as a job, the old page expects a plain answer, and it shows
  "No answer." instantly. Every page now carries a build stamp and compares
  it with `/api/version`; when the server has moved on, the page says
  "Charta was updated while this window was open — reload" with a Reload
  button. The Electron tray has a "Reload window" item for the same reason.
  Files: `charta/web/app.py`, `charta/web/static/app.js`, `desktop/main.js`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 212 passed.

- 2026-10-21: **no more "No answer."** A model that has learned to call tools
  sometimes answers the *final* prompt with a tool call too — Charta was
  showing that JSON as if it were the answer, and a model that only ever calls
  tools left the user with nothing. Now every tool call is stripped from an
  answer, the agent asks for a final answer when the rounds run out, the
  grounded retrieval path is used whenever the model's reply is not a real
  answer, and the chat never shows a bare "No answer." — it says where it
  stopped instead. Files: `charta/core/agent.py`, `charta/core/ask.py`,
  `charta/web/app.py`, `charta/web/static/app.js`, `tests/test_agent.py`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 211 passed; a model stuck in a
  tool loop, a model that returns nothing and a model that only chats were
  each run through the web API and each produced a real answer.

- 2026-10-21: **the model calls the tools itself.** Charta hands the model a
  catalogue of the folder's metadata (every file with its description, tags
  and fields) and three tools — `search_index`, `read_file`, `list_files` —
  and runs whatever it asks for: search the index, read a file (from the
  index, so it is instant), list what is there. The model then answers from
  what it read, and the files it used become the citations. The protocol is
  plain text (a JSON action), so it works with every OpenAI-compatible
  endpoint, including local models without function-calling support; a model
  that never calls a tool still gets the grounded answer from the retrieval
  path. Every call appears in the Ask timeline ("Calling search_index(q=
  'sponsorship 2026') → 1 match"), and the Ask page lists the tools it has.
  Files: `charta/core/agent.py`, `charta/core/llm.py` (multi-turn `chat`),
  `charta/web/app.py`, `charta/web/static/app.js`, `charta/web/static/app.css`,
  `charta/cli.py`, `README.md`, `tests/test_agent.py`. Verified: `pytest -q` 208
  passed; the whole loop (search → read → answer, with citations) was run
  against a scripted model.

- 2026-10-21: **a metadata index, a real search, and a work timeline.** Every
  file Charta reads is now described once and kept in the folder's own SQLite
  index (`.charta/index.db`): description, document type, tags, the fields
  found in it (date, vendor, amount, currency, category), and the extracted
  text in chunks. Ask works from that index instead of re-reading the folder
  (and fills it in when it has to), so the AI is handed the metadata and text
  of the few files that match instead of the whole folder. New **Search** page
  and `/api/search`: find files by name, tag, description, field or content,
  with clickable results — Read in place, Open in the system app, Ask about
  that file, or show it in Explorer. The **Ask** screen now shows a work
  timeline (read the index → matched N files → asking provider/model → answer)
  as a job the UI polls, with the steps appearing as they happen. Files:
  `charta/core/index_db.py`, `charta/core/meta.py`, `charta/core/ask.py`,
  `charta/core/pipeline.py`, `charta/core/tools.py`, `charta/web/app.py`,
  `charta/web/static/app.js`, `charta/web/static/app.css`, `desktop/main.js`,
  `DESIGN.md`, `README.md`, `tests/test_index_db.py`, `tests/test_web_ui.py`.
  Verified: `pytest -q` 202 passed; a folder indexed through Ask is immediately
  searchable, and the work timeline was checked against a live server.

- 2026-10-21: **Ask gives an answer again, and says what it did.** Asking
  about a big folder (here: the repository itself) meant reading every file —
  images included, each one a slow vision call — so the request took minutes
  and the page sat there with no answer and no error. Now the index is bounded
  (200 files, 45 s budget) and cached per folder: the first question reads the
  folder, every later one is instant, and the answer reports how many files
  were read, whether it was cached, which provider and model answered, and
  whether some files were left out. The UI shows "reading the folder…" and, on
  failure, the error in the chat instead of silence. `charta ask` prints the
  same summary. Also: a provider whose `/models` route does not answer (slow
  hosts like OpenRouter) is no longer reported as "down" — a 401 counts as
  alive. Files: `charta/core/ask.py`, `charta/core/llm.py`,
  `charta/core/doctor.py`, `charta/web/app.py`, `charta/web/static/app.js`,
  `charta/cli.py`, `tests/test_web_ui.py`. Verified: `pytest -q` 197 passed.

- 2026-10-21: **Ask is now strictly about one folder.** Two bugs made "no
  answer": an empty folder parameter meant `Path("")` = *the current
  directory*, so the Ask page (reached from the sidebar on the Folders page,
  where no folder is in the URL) silently indexed whatever the app was sitting
  in — the whole repository — and the request took forever. `build_index` now
  refuses an empty or missing folder, `/api/ask` answers "pick a folder first",
  the Ask page offers the watched folders when none is chosen, the sidebar only
  shows folder pages once a folder is picked, and every answer says which
  folder, provider and model produced it. Also: the API key now comes from
  `config.toml` first and the environment second (the file is yours and
  git-ignored), as asked. Files: `charta/core/ask.py`, `charta/core/config.py`,
  `charta/web/app.py`, `docs/WINDOWS.md`, `tests/test_web_ui.py`,
  `tests/test_config_llm.py`. Verified: `pytest -q` 195 passed; a folder with
  `sponsorship_2026.txt` answers "i want to know about the 2026 sponsorship"
  with the file and page cited.

- 2026-10-21: **`config.toml` belongs to the user (one file, no overlay).**
  `config.toml` was tracked in git, so `git pull` kept restoring the file
  people had edited — which is why changing the provider appeared to do
  nothing. It is now git-ignored, and the repository ships
  `config.toml.example` as the template. A fresh clone runs on the built-in
  defaults until you copy the example. The lookup order is now
  `CHARTA_CONFIG` → next to the installed package → the per-user state dir →
  the current directory, so an installed app finds the file too, and
  `charta testmodel` / `charta doctor` print the file in use. The
  `config.local.toml` overlay from the previous commit was removed again: one
  config file, and it is yours. Files: `charta/core/config.py`,
  `charta/core/doctor.py`, `charta/cli.py`, `.gitignore`, `AGENTS.md`,
  `README.md`, `docs/WINDOWS.md`, `config.toml.example`,
  `tests/test_config_llm.py`. Verified: `pytest -q` 192 passed.

- 2026-10-21: **`config.local.toml` — settings that are yours.** `config.toml`
  lives in the repository, so `git pull` kept restoring the file people had
  edited (which is why "I set the provider to openrouter" had no effect: the
  edit was gone). A new `config.local.toml` next to it is git-ignored, is never
  overwritten, and is layered over `config.toml` section by section.
  `config.local.toml.example` is the template. `charta testmodel`, `charta
  status` and `charta doctor` now print which config files are in use, so a
  stale or missing config is obvious. Files: `charta/core/config.py`,
  `charta/core/doctor.py`, `charta/cli.py`, `.gitignore`,
  `config.local.toml.example`, `README.md`, `tests/test_config_llm.py`.
  Verified: `pytest -q` 193 passed; a local file switching the provider to
  openrouter was seen by `testmodel` and `status`.

- 2026-10-21: right-clicking a folder while Charta is already open now opens
  *that* folder in the running window. Before, the second instance only
  focused the existing window and dropped the folder on the floor, so the
  right-click looked like it did nothing (the window stayed on whatever page
  it was showing). The shell reads the folder out of the other instance's
  command line and navigates to it; the argument parsing moved to
  `desktop/lib/args.js` so it can be unit-tested.
  Files: `desktop/main.js`, `desktop/lib/args.js`, `desktop/test/unit.test.js`,
  `charta/shell/desktop.py`. Verified: `pytest -q` 192 passed;
  `node --test test/unit.test.js` 9 passed.

- 2026-10-21: **watching an empty folder now sticks.** The setup screen fired
  a second request to start the watcher and ignored its answer, so a failed
  watch still said "charter ready — watching" while the tray said "nothing
  watched yet". The charter endpoint now starts the watch itself and reports
  the real state; the setup card only claims to be watching when it is, and
  the Overview says "this folder is empty — Charta is watching it" instead of
  "scanning". The launcher also hands over to the shell and exits as soon as
  the window is up, so the console Explorer opens no longer lingers for the
  whole session (the session file keeps pointing at the live window).
  Files: `charta/web/app.py`, `charta/web/static/app.js`,
  `charta/shell/desktop.py`, `tests/test_web_ui.py`, `tests/test_electron.py`.
  Verified: `pytest -q` 192 passed.

- 2026-10-21: **stop the double window and the stale window.** A Charta left
  running in the tray (from before an update) held port 8123 and Electron's
  single-instance lock, so the next `charta open` could not start: the shell
  quit silently, the launcher took it for a crash and opened a browser as
  well — the old window and a new browser side by side. Now the shell exits
  with code 42 when another instance owns the window, the launcher says
  "Charta is already running — that window came to the front" and does *not*
  open a browser; the launcher also reports an already-running instance before
  it starts, and Settings shows when the backend started, so a window running
  old code is obvious. Files: `desktop/main.js`, `charta/shell/desktop.py`,
  `charta/web/app.py`, `tests/test_electron.py`. Verified: `pytest -q` 190
  passed.

- 2026-10-21: the desktop shell now knows the new screens. The Electron window
  renders the server's pages (the sidebar is server-rendered), so a running
  app keeps showing the old navigation until the backend is restarted — but
  `desktop/main.js` had its own route list for the smoke run and the
  screenshots, and it did not include `/folders`, `/files` or `/history`.
  Both that list and `tools/ui_check.py` now cover all twelve screens, the
  tray menu can jump to the Folders page, and a test guards that the shell and
  the server know the same routes. Files: `desktop/main.js`,
  `tools/ui_check.py`, `tests/test_electron.py`. Verified: `pytest -q` 189
  passed; `node --test test/unit.test.js` 8 passed.

- 2026-10-21: per-folder mode switch. The mode chip on the Folders page is now
  a button: it flips one folder between suggest and auto (`POST /api/mode`,
  writing the charter's mode back to `.charta/charter.md`), so auto mode stays
  an explicit, per-folder opt-in. Files: `charta/web/app.py`,
  `charta/web/static/app.js`, `tests/test_web_ui.py`. Verified: `pytest -q`
  188 passed.

- 2026-10-21: **Bulk scans with progress, and a fix for two git races.**
  `POST /api/scan` now runs in the background and reports progress
  (`/api/scan/status`: done/total/current file), so a folder with hundreds of
  files no longer freezes the UI — the Files and Folders pages show a progress
  bar. Two history bugs found while testing and fixed: the exclude file that
  keeps `.charta/` out of the index was written only when the repository was
  created, so a folder that already had one started recording Charta's own
  bookkeeping (and the first 12 files shown hid the real ones); and two
  commits at once fought over git's index lock. Now the exclude file is
  rewritten on every commit and each folder has one git lock. Settings gained
  a "Folders" section showing where the watched-folder registry lives.
  Files: `charta/core/history.py`, `charta/core/watchd.py`, `charta/web/app.py`,
  `charta/web/static/app.js`, `README.md`, `tests/test_history.py`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 186 passed.

- 2026-10-21: **Git-style history + file tools.** Every watched folder can carry
  a private git repository at `.charta/git` (work tree = the folder, `.charta/`
  excluded from the index): Charta commits after it indexes files, moves one,
  edits one, trashes one, rebuilds outputs or undoes a move, with a readable
  message ("charta: moved receipts/scan.pdf → Invoices/invoice.pdf — moved
  because it is an electricity bill dated March 2026"). New `/history` page
  lists the trail (date, short sha, message, files touched); an old version of
  a file can be restored with one click — a restore is a copy, and the current
  file is kept as `<name>.charta-old`. New file tools (`charta/core/tools.py`):
  read (text, PDF, DOCX, vision summary), edit in place (old version kept), and
  "Move to trash" into `.charta/trash/` with "Bring back" — nothing is ever
  deleted, per the safety rules. History is on by default (`[app] history`,
  `CHARTA_HISTORY=0` to disable) and needs git on PATH; without git Charta
  works exactly as before. Files: `charta/core/history.py`,
  `charta/core/record.py`, `charta/core/tools.py`, `charta/core/watchd.py`,
  `charta/core/mover` call sites, `charta/core/config.py`, `config.toml`,
  `charta/web/app.py`, `charta/web/icons.py`, `charta/web/static/app.js`,
  `charta/cli.py`, `DESIGN.md`, `tests/test_history.py`, `tests/test_tools.py`,
  `tests/test_web_ui.py`. Verified: `pytest -q` 185 passed; a demo folder's
  history, restore, edit and trash were exercised end to end.

- 2026-10-21: **Folders dashboard + Files view + a registry that remembers.**
  New `/folders` page lists every folder Charta knows: how many are watched,
  each folder's purpose, mode, files/indexed/pending/gaps/moves, watching-since
  and last-scan, with Open/Files/Ask/Scan/Stop-watching actions and an inline
  ask box per folder. New `/files` page lists every file in a folder with its
  index state and why, and a reader that shows extracted text, PDF pages or a
  vision summary (`/api/file/read`, traversal outside the folder refused).
  `watchlist.py` now keeps a record of every folder with a `watching` flag, so
  unwatching pauses instead of forgetting and re-watching resumes the existing
  analysis (charter, proposals and journal live in the folder's `.charta/`).
  Nav gains Folders and Files (DESIGN.md §2/§5 updated). Files:
  `charta/core/watchlist.py`, `charta/web/app.py`, `charta/web/icons.py`,
  `charta/web/static/app.js`, `DESIGN.md`, `tests/test_web_ui.py`,
  `tests/test_watchlist.py`. Verified: `pytest -q` 168 passed; the Folders and
  Files pages were rendered against a demo folder.

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

## In Progress

- Windows verification of this wave on a real machine: the global Ctrl+Space
  from the tray, Moonshine against the model the user downloaded, and the
  settings round-trip on real config.toml (`git pull; charta stop; charta open .`).

## Next Up

1. (user) Try the voice wave on Windows: Ctrl+Space from the tray, Moonshine
   transcription, the editable Settings page, and the answer-ready
   notification.
2. (user) Try the new Ask on Windows: the chat strip, continuing a
   conversation, follow-up memory, and opening a source chip.
3. Windows visual pass: Explorer menu, tray, Mica/title bar, close-to-tray,
   then a recorded 60–90s before/after demo (`charta demo` → sorted folder +
   output).

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

- 2026-10-25: the Settings UI writes the user's `config.toml` directly
  (atomic write, one `.toml.bak` backup) instead of a shadow override file.
  Why: AGENTS says one config file, and a second layer would make the
  relationship between ".env vs UI vs file" impossible to reason about. GET
  reports whether a key exists, never the key; env keys stay env's business
  and are never copied into the file by the UI.

- 2026-10-24: conversations are files, not a hidden database —
  `.charta/chats/<id>.json` inside the folder the chat is about. Why: same
  principle as the charter and journal — memory the user owns, can open,
  move, or edit; survives with the folder; no extra runtime.
- 2026-10-24: follow-up memory sends the last 6 turns capped at 1600
  characters each, as plain user/assistant messages. Why: the model must
  see what it said, but a full chat replay would drown the index catalogue
  in tokens; the cap keeps prompts small and predictable on 4B-class
  models.
- 2026-10-24: the ask API distinguishes `chat:"new"`, an existing id, and
  an empty chat (ephemeral). Why: the dashboard's per-folder ask boxes are
  one-shot questions — saving every one would litter the strip with
  throwaway conversations.
- 2026-10-23: answer rendering moved from "parse whatever markdown the
  model wrote" to a model-driven blocks protocol (`FINAL: {"blocks":[...]}`,
  Pydantic-validated, five block types). Why: the model kept emitting
  block-level markdown the small local renderer could not fully cover
  (`###`, raw tables), and tolerant parsing is an arms race — typed content
  removes the parsing entirely; graceful fallback keeps answers flowing.


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

- 2026-10-25: the previous voice wave shipped half-wired: the popup called
  `window.__recordAudio`, a function that never existed (the user hit
  "not a function" on first press), and `stt.py` had an illustrative
  ElevenLabs endpoint (an up-arrow Unicode dash inside the URL, no real
  upload). Root cause: the edits marched file-by-file with print-based
  confirmations instead of a single wired path proven end to end, and a
  heredoc quoting bug left the frontend untouched while later reports were
  still "js ok". Lesson: a wave is not done because its pieces each parse —
  grep every identifier the generated UI references, then exercise the
  actual flow (press → record → server → text → composer) before calling it
  delivered. The tests in `tests/test_settings_voice.py` now exercise the
  exact HTTP surfaces the popup uses.
- 2026-10-24: building `onclick="openChat('<id>')"` as a JS string meant
  nested quoting — the `\\'` escapes landed literally in app.js and
  `node --check` failed (missing `)` after argument list), and a later
  citation-chip rewrite failed the same way for the same reason. Fix: no
  inline strings — chips carry `data-*` attributes and the handler reads
  `this.dataset`; values are `encodeURIComponent`-escaped with `'` forced
  to `%27` (encodeURIComponent deliberately leaves `'` unencoded, which
  would still terminate the attribute). Lesson: any time generated HTML
  needs to call a function with a value, ship the value in a data
  attribute; string-splicing arguments into attributes is a parsing bug
  waiting to happen.
- 2026-10-24: several Python edits used `str.replace` with a code anchor
  and reported "ok" even when the anchor had already changed — the chat-id
  parameter, the history call, and the chats import all silently never
  landed, and three test waves (state "failed", `chat_id is not defined`,
  `chats is not defined`) were the only symptom. Lesson: assert the anchor
  was found before writing (`if old not in s: raise`), and let the test
  suite, not the print, confirm an edit took effect.

- 2026-10-23: the ask rewrite left a duplicate old `window.askFolder` behind;
  the later definition won, calling the new `watchJob(job, work)` with a
  callback as `work` — the user saw "work.add is not a function" on every
  question. Lesson: after a heavy block replacement, grep for all
  definitions of every entry point it declared; a test now asserts exactly
  one definition per name and that entries route through askOnce.

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
