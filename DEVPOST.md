---
title: "Charta: right-click a folder and it files itself"
published: false
description: "A local-first AI folder: right-click any folder in Windows, and the files you drop in get renamed, filed into the right subfolder and indexed — so questions are answered from that index, with citations. Runs on Gemma via Ollama, or any OpenAI-compatible provider, local or cloud. Built for the Hacktoberfest Open-Source AI Challenge Week 3."
tags: devchallenge, hf26challenge
cover_image: 
---

*Hacktoberfest Open-Source AI Challenge, Week 3 — Slow and Steady.*
[Demo video](https://youtu.be/Y1YP2tSMvu4) · [Source](https://github.com/abbasmir12/charta) · [How to run it](#code)

> **11:47 pm. A folder called `Freelance`. Forty-two files. Zero subfolders.**
>
> `facture-EDF-janv-2026 (1).pdf`. `Scan_0031.pdf`. `new_document(2).pdf`. A photo of the meter, a bank export, a lease, five rent receipts, a plumber's invoice, a renovation quote, a warranty. Everything you will ever need is already in that folder — and nothing in it is findable.

Every computer has this folder. Not a knowledge base, just a pile. Sorting it is unpaid administrative labour, and doing it well asks for exactly the kind of attention nobody has at midnight.

**Charta turns that pile into a folder that files itself.**

> Right-click it in Explorer → **Watch with Charta** → *"This is where I keep my freelance paperwork: invoices, rent, insurance."*
>
> That one sentence becomes `.charta/charter.md` — plain Markdown, inside the folder, yours to edit. Everything below follows from it.
>
> From then on, **nothing enters that folder unseen.** You drop a file in; Charta reads it, works out what it is, renames it if the name is garbage, files it into the right folder and subfolder, and writes a row for it into the folder's own index. You approve, it moves.
>
> And when you ask *"how much did I spend since January?"*, it does not open forty PDFs. It reads the index — and answers with the amount, the file, and the page it came from.

## What I Built

Charta is a **magic folder**. Any folder on your machine — `D:\Freelance`, `C:\Users\me\Desktop\paperwork`, a student's `Lectures` — can become an intelligent folder: one you point at in Explorer, charter in a sentence, and then simply use. The AI is local (a Gemma model through Ollama), so the watching, the reading and the answering all happen on your own disk.

```
D:\Freelance\
  .charta\
    charter.md      <- the folder's purpose, human-editable
    journal.jsonl   <- every move, undoable
    index.db        <- what each file contains
  Invoices\
    2026-04-edf-electricity.pdf
    2026-05-orange-internet.pdf
  Rent\
    2026-04-receipt.pdf
```

### Nothing enters that folder unseen

Once a folder is watched, every file that lands in it — dragged from Downloads, saved from a browser, scanned from a printer, unzipped from an email — goes through the same loop:

> 1. **A file lands.** You drag an invoice, a lecture, a scan, a spreadsheet into the folder.
> 2. **Charta waits until it is fully written**, then reads it — PDF text, DOCX, XLSX, images through the model's vision.
> 3. **It proposes a name and a place** based on the charter: `new_document(2).pdf` → `Invoices/2026-04-edf-electricity.pdf`. Nothing moves until you approve it — default mode is *suggest*, so the folder does the thinking and you keep the authority.
> 4. **On approval it moves and renames** — never deletes, never overwrites, always with a numeric suffix on collision and an entry in the undo journal.
> 5. **It writes down what is inside** — document type, vendor, date, amount, tags, and the text itself. That is the index.
> 6. **Every change stays on the record** — the journal for moves (one click to undo) and a local history for moves, renames, edits and undo, committed with a plain-English reason. A bad decision never costs you a file.

### The index is the trick

This is the part that makes the folder feel intelligent instead of merely tidy. Charta does its reading **once**, when a file arrives, and keeps what it learned in `.charta/index.db` — a plain SQLite file that belongs to that folder and travels with it.

One row per file: what it is, what is inside it, which fields were found, and the text itself, chunked by page.

```text
path         Invoices/2026-04-edf-electricity.pdf
name         (was: new_document(2).pdf)
doc_type     electricity bill
description  EDF electricity bill for April 2026, due 15/05/2026
fields       vendor EDF · amount 82.50 EUR · date 2026-04
tags         edf electricity invoice 2026
chunks       p1  "Facture EDF - avril 2026 / Consommation kWh: 04711 / Montant TTC: 82,50 EUR"
```

That row is the whole point. When you ask a question, the agent does not walk the folder and it does not stuff your PDFs into a context window. It searches this table — keyword/BM25 plus regex over dates, months, amounts and document types, with each file's description as a strong signal — and hands the model the metadata and the few matching chunks that actually matter.

> The difference is not subtle.
>
> **Without an index:** open the folder, pick files by name, open each one, hope. Or paste your rent contract into a cloud chat and lose it forever.
>
> **With an index:** one query over a table the folder wrote about itself, a handful of matching rows, an answer in seconds, a citation you can click.
>
> It also means questions get *cheaper*, not more expensive: the AI paid for the reading once, at drop time, and every later question reads text it already understood.

### Then ask it anything

> **You:** how much did I spend on electricity this year?
>
> **Charta:** €322.00 across four EDF bills — January (€79.40), February (€71.20), April (€82.50), May (€88.90).
>
> *Sources: the four EDF bills in `Invoices/`, each with its page number.*
>
> And it notices what is **not** there: *"there is no electricity bill for March — the folder expects one per month."*

That last line is the feature I did not plan and now use most. A folder that knows what it is *supposed* to contain can tell you what is missing.

## Demo

{% embed https://www.youtube.com/watch?v=Y1YP2tSMvu4 %}

> This demo shows a folder being watched with Charta — and how intelligent that makes it. I drop a pile of different invoices into it, and Charta creates an **Invoices** folder, moves every invoice in there, renames them, and indexes each one. From that moment the folder can answer questions about them.

## Code

{% embed https://github.com/abbasmir12/charta %}

```bash
git clone https://github.com/abbasmir12/charta
cd charta
pip install -e .
charta open .          # native window on Windows; `charta serve` anywhere
```

> No account and no sign-up. The default provider is Ollama on `localhost` with a local Gemma model, but Charta speaks the **OpenAI-compatible API**, so any provider works — local ones like Ollama, LM Studio, llama.cpp or vLLM, or hosted ones like OpenRouter, Groq, Together, DeepSeek or OpenAI. Change `[llm]` in `config.toml` and that is the whole migration.
>
> `charta demo` builds a messy sample folder, charters it, proposes, approves and writes the output — fully offline, no model required, so you can see the whole loop in one command.

## How I Built It

Open source AI is the engine here, not a badge stuck on the side.

> **The model — any provider you want, because it is OpenAI-compatible.** Charta has exactly one HTTP client, and it speaks the standard OpenAI-compatible API. Out of the box that means a local Gemma model through Ollama, but it is the same client pointed at LM Studio, llama.cpp or vLLM locally, or at OpenRouter, Groq, Together, DeepSeek or OpenAI in the cloud. Nothing is hard-coded: provider, base URL, key and model names live in one git-ignored `config.toml` owned by the machine (or in the Settings page), so `git pull` can never undo your choice, and swapping providers is an edit, not a rewrite.
>
> **The agent.** Ask is a real agent, not one big prompt. Charta hands the model a catalogue of the index plus three tools — `search_index`, `read_file`, `list_files` — and runs whatever it asks for. The model answers from what it actually found, and the files it read become the citations. Every tool call is visible in the UI as it happens.
>
> **The memory.** A file the user owns: `.charta/charter.md` (Markdown + YAML front-matter), `.charta/journal.jsonl` for undo, and a folder-local SQLite index for what each file contains. No vector database, no embeddings. Retrieval is keyword/BM25 plus regex for dates, months, amounts and document types, with a short description per file. Fast, deterministic, explainable — and it runs on a 4B model without a GPU budget.
>
> **The reading.** PyMuPDF for PDF text, Gemma vision for scanned pages and photos, RapidOCR as fallback, `openpyxl` for spreadsheets and a stdlib DOCX reader. One `extract` interface hides all of it.
>
> **The voice.** Push-to-talk on Ctrl+Space — a global toggle inside the desktop shell, even from the tray. Local Whisper by default, system speech as fallback, ElevenLabs as a clearly labelled cloud opt-in. Transcripts land in the composer and send themselves.
>
> **The window.** FastAPI serving plain HTML, CSS and vanilla JS. No bundler, no CDN, fonts and icons bundled locally. The Electron shell in `desktop/` wraps the same UI with a tray and hardened defaults; the UI still works in a browser without it.
>
> **The safety.** Suggest by default. Never delete, only move or copy. Every move journalled and undoable in one click. Protected paths (Windows, Program Files, AppData, drive and profile roots) refused with a friendly screen instead of an error dump. Sensitive content — ID numbers, card numbers, IBANs, passwords — detected, kept out of the index, and the file flagged in the proposals.

**Sentry Agent Tracing** is the piece I am proudest of, because it should not have worked. Charta's HTTP client is hand-written, so Sentry's auto-instrumentation (which monkey-patches the `openai` package) would never fire. I instrumented the loop by hand instead:

> - `gen_ai.invoke_agent` — `invoke_agent charta-ask`, wrapped around the whole run.
> - `gen_ai.chat` — `chat {model}`, at the single choke point every model call passes through, carrying token counts, finish reasons and the response model.
> - `gen_ai.execute_tool` — `execute_tool {tool}` with arguments, result and error status.
> - The folder's chat id becomes the Sentry conversation id, so multi-turn chats group together.
> - The agent runs in a detached context, so its trace is a root transaction instead of a child of `POST /api/ask` — which is what actually makes it show up in the transaction list.
> - Opt-in to the point of invisibility: no DSN means every helper is a silent no-op, and prompts and answers stay on disk unless `record_inputs`/`record_outputs` are explicitly flipped.

## Why Does Open Innovation Matter?

Because the folder I am describing is the one folder you can never upload.

Rent contracts, bank statements, meter readings, insurance policies, a scan of an ID card. That is the folder where privacy is not a preference — it is the entire point. A closed API could read it perfectly well. But the moment you paste a rent contract into a chat box, that contract leaves your machine forever and you have no way to know who reads it next.

> Open weights running locally change the arithmetic completely.
>
> The model reading my invoices is a Gemma model sitting on my own laptop. It works with no internet, costs nothing per question, and sends nothing anywhere. The only network call Charta makes is to the LLM endpoint the user configured — and to Sentry only if they paste their own DSN into their own config.
>
> The AI's memory is a file I can open in Notepad. If I dislike how it organised something, I edit the charter and it behaves differently tomorrow. No fine-tuning pipeline, no vendor, no monthly bill, no terms of service to trust.

That is what open innovation made possible: an assistant for the most private folder on your computer that a stranger can reproduce on a laptop with no internet and no money.

## The Lazy Payoff

Real numbers from a week of using it on my own invoice folder:

> - Sorting a batch of ten invoices: **~15 minutes** of dragging, renaming and guessing → **one scan, one approve click, under a minute.**
> - Finding one specific invoice: "open five files and hope" → one question, answer with file and page.
> - The gap detector caught a **missing March electricity bill** I had not noticed for two weeks.
> - The purpose output wrote the receipts spreadsheet I actually had to deliver.

The honest caveat: the **first** run is not lazy at all. You charter the folder, you scan it, you review the proposals. That is the Slow and Steady bargain — front-load the boring thinking so every day after it is one drag and one click. Worth it.

## Prize Categories

> - **Gemma — Best Use of Gemma** *(primary)*. Gemma is the model that reads, classifies, names and answers. It runs locally through Ollama: no key, no cloud, no per-token bill.
> - **ElevenLabs — Best Use of ElevenLabs** *(secondary)*. Voice charter creation and push-to-talk questions, with ElevenLabs speech-to-text as the opt-in cloud option beside local Whisper.
> - **Sentry — Best Use of Sentry Agent Tracing**. Manual `gen_ai.invoke_agent` / `gen_ai.chat` / `gen_ai.execute_tool` instrumentation of a hand-written client, token and latency attributes, conversations grouped by chat id, and prompts kept off the wire by default.
