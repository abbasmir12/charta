"""The agent: Charta gives the model tools and lets it use them.

The model is handed a catalogue of the folder's metadata (what is in the index,
with descriptions, tags and fields) and a small set of tools:

  * ``search_index(q)``  — search the index by name, tag, description, field
                           or content; returns matching files with metadata
  * ``read_file(path)``  — read one file's text (from the index, so it is
                           instant and never re-reads the folder)
  * ``list_files()``     — the catalogue again, in a compact form

The model calls them, Charta runs them, and the model answers from what it
found. Every call is recorded, so the UI can show the work: "called
search_index('sponsorship') → 3 files".

The protocol is plain text (a JSON action), so it works with every
OpenAI-compatible endpoint — including local models with no function-calling
support. A model that never calls a tool simply answers, and the answer is
still checked against the index.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, TypeAdapter, ValidationError

from . import index_db
from . import observability as obs
from .ask import Citation, chunk_text
from .classify import Proposal
from .llm import LLMClient

MAX_ROUNDS = 5
CATALOGUE_LIMIT = 80

TOOL_SPECS: list[dict] = [
    {
        "name": "search_index",
        "description": ("Search this folder's metadata index: file names, "
                        "descriptions, tags, extracted fields (date, vendor, "
                        "amount) and the text inside. Returns matching files."),
        "parameters": {"q": "the words to look for", "limit": "how many results"},
    },
    {
        "name": "read_file",
        "description": "Read the text of one file in this folder (from the index).",
        "parameters": {"path": "the file path, relative to the folder"},
    },
    {
        "name": "list_files",
        "description": "List the files in the index with their description and tags.",
        "parameters": {},
    },
]

SYSTEM = """You are Charta, working inside one folder on the user's computer.

You have tools:
{tools}

How to work:
1. The CATALOGUE below says what is in the folder (name, description, tags,
   fields). Read it first.
2. To find out more, call a tool. To call one, reply with exactly one JSON
   object and nothing else, for example:
   {{"tool":"search_index","args":{{"q":"sponsorship 2026"}}}}
   or
   {{"tool":"read_file","args":{{"path":"Receipts/receipt_edf.txt"}}}}
3. Use the results to pick the files worth reading, then read them.
4. When you can answer, your final answer must be ONE JSON object with a
   "blocks" array that describes the answer for display. Plain text only —
   never use markdown symbols like ### or | or ** inside these strings.
   Use ONLY these block shapes:
   {{"type":"heading","level":1,"text":"Big title"}}
     (level 1: main headline, 2: section headline, 3: small side heading)
   {{"type":"p","text":"One paragraph. Keep exact dates and amounts."}}
   {{"type":"list","items":["point one","point two"]}}
   {{"type":"table","columns":["What","Value"],"rows":[["Rent","900 EUR"]]}}
   {{"type":"facts","entries":[{{"label":"Amount","value":"2500 EUR"}}]}}
   Guide: key figures go in a facts block, comparisons in a table, steps or
   points in a list, everything else in p blocks. Cite the files you used
   inside the text, like [file.txt p1]. Never invent a fact. If the folder
   does not contain the answer, say so plainly in a p block.
   Block text rules: plain sentences only — never "###" or "|" separators or
   markdown symbols, and never paste long raw text from the files (whole URLs,
   form fields, OCR lines). Summarise what a file means in your own words.
5. The last line of your answer must be exactly:
   FINAL: {{"blocks":[...]}}

6. After that FINAL line, you may help organise the folder — propose only,
   never claim you changed anything; the user approves in Review. Add these
   lines, one per line, only when genuinely helpful:
   RENAME: current_file.txt -> clearer_name.txt
   MOVE: file.txt -> Subfolder/          (creates the folder if needed)
   GAP: what is missing from this folder (e.g. "no electricity bill for March")

CATALOGUE:
{catalogue}"""


@dataclass
class ToolCall:
    name: str
    args: dict
    result: str = ""
    ok: bool = True


@dataclass
class AgentResult:
    answer: str = ""
    blocks: list[dict] = field(default_factory=list)
    raw: str = ""  # the model\'s final text as sent (protocol + org lines)
    citations: list[Citation] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    used_tools: bool = False
    files: list[str] = field(default_factory=list)


def catalogue(folder: str | pathlib.Path, limit: int = CATALOGUE_LIMIT) -> str:
    """A compact listing of the index: what is in the folder, with metadata."""
    rows = index_db.files(folder)
    if not rows:
        return "(the folder is empty — nothing has been indexed yet)"
    lines = []
    for item in rows[:limit]:
        bits = [item.get("description") or item.get("doc_type") or "document"]
        fields = item.get("fields") or {}
        field_bits = [f"{k} {v}" for k, v in fields.items() if v and k != "category"]
        if field_bits:
            bits.append("; ".join(field_bits))
        tags = ", ".join(item.get("tags", [])[:5])
        if tags:
            bits.append(f"tags: {tags}")
        lines.append(f"- {item['path']} — " + " | ".join(bits))
    if len(rows) > limit:
        lines.append(f"- …and {len(rows) - limit} more file(s)")
    return "\n".join(lines)


def strip_tool_calls(text: str) -> str:
    """Remove any tool-call JSON from a reply.

    A model that has learned to call tools sometimes answers the *final*
    prompt with a tool call too. That is not an answer, and showing it to the
    user as one is worse than saying nothing.
    """
    if not text:
        return ""
    cleaned = text
    for _ in range(4):
        action = _json_action(cleaned)
        if not action:
            break
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            break
        cleaned = (cleaned[:start] + cleaned[end + 1:]).strip()
    return cleaned.strip()


def _json_action(text: str) -> tuple[str, dict] | None:
    """Find a tool call in the model's reply.

    The JSON may contain nested objects (``{"tool":"read_file","args":{...}}``),
    so the braces are matched by depth rather than by a flat pattern.
    """
    if not text:
        return None
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start:end + 1])
                    except ValueError:
                        break
                    if isinstance(data, dict) and data.get("tool"):
                        args = data.get("args")
                        if not isinstance(args, dict):
                            args = {}
                        return str(data["tool"]), args
                    break
    return None


def _tool_description(name: str) -> str:
    """The catalogue text for one tool (goes on the trace, not to the model)."""
    for spec in TOOL_SPECS:
        if spec["name"] == name:
            return spec["description"]
    return ""


def run_tool(name: str, args: dict, folder: str | pathlib.Path) -> str:
    """Run one tool and return what it found (as text for the model)."""
    if name == "search_index":
        query = str(args.get("q") or args.get("query") or "").strip()
        limit = int(args.get("limit") or 10)
        if not query:
            return "search_index needs something to look for."
        hits = index_db.search(folder, query, limit=limit)
        if not hits:
            return f"search_index('{query}') → no match in the index."
        lines = [f"search_index('{query}') → {len(hits)} match(es):"]
        for hit in hits:
            fields = ", ".join(f"{k} {v}" for k, v in (hit.get("fields") or {}).items() if v)
            lines.append(f"  - {hit['path']} — {hit.get('description', '')}"
                         + (f" | {fields}" if fields else ""))
        return "\n".join(lines)
    if name == "read_file":
        path = str(args.get("path") or args.get("file") or "").strip()
        if not path:
            return "read_file needs a path."
        text = _read_from_index(folder, path)
        if text is None:
            return (f"read_file: '{path}' has no text in the index (an image or a "
                    "format without extracted text). Use search_index to find a "
                    "file with real text, or answer from the catalogue.")
        return f"read_file('{path}') →\n{text}"
    if name == "list_files":
        return "list_files() →\n" + catalogue(folder)
    return f"Unknown tool '{name}'."


def _read_from_index(folder: str | pathlib.Path, path: str) -> str | None:
    """The stored text of a file (no re-reading of the folder)."""
    rows = [c for c in index_db.chunks(folder) if c[0] == path]
    if not rows:
        return None
    return "\n".join(f"[p{page}] {text}" for _, page, text in rows[:12])


def ask_with_tools(question: str, folder: str | pathlib.Path, client: LLMClient,
                   steps: list[dict] | None = None, rounds: int = MAX_ROUNDS,
                   history: list[dict] | None = None) -> AgentResult:
    """Let the model use the folder's tools, then answer.

    ``history`` carries the previous turns of the conversation (model
    messages), so follow-up questions — "and what about June?" — land on a
    model that remembers the exchange before. A fresh question has none.
    Falls back to a plain answer when the model does not call any tool.
    """
    run_span = obs.agent_run(question)  # no-op unless Sentry is configured

    def note(kind: str, text: str) -> None:
        if steps is not None:
            steps.append({"kind": kind, "text": text})

    tool_text = "\n".join(f"- {t['name']}({', '.join(t['parameters']) or 'no arguments'}): "
                          f"{t['description']}" for t in TOOL_SPECS)
    system = SYSTEM.format(tools=tool_text, catalogue=catalogue(folder))
    note("work", "Showing the model the index catalogue.")
    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": question})
    calls: list[ToolCall] = []
    used_files: list[str] = []
    answer = ""
    retried_json = False
    for round_no in range(rounds):
        try:
            res = client.chat(messages, system=system)
        except Exception as e:  # noqa: BLE001 — fall back to the plain path
            note("warn", f"The model call failed: {e}")
            break
        text = (res.text or "").strip()
        if not text:
            note("warn", "The model said nothing.")
            break
        action = _json_action(text)
        if not action:
            answer = strip_tool_calls(text)
            # The protocol asks for a blocks JSON. If the model clearly tried
            # it and missed — or plainly ignored it and wrote block-level
            # markdown — one corrective round. Then graceful fallback.
            parsed = structured_answer(answer)
            is_only_paragraphs = (parsed[1] and
                                  all(b.get("type") == "p" for b in parsed[1]))
            tried_but_missed = '"blocks"' in answer and is_only_paragraphs
            ignored_protocol = (not tried_but_missed
                                and _answer_needs_format_retry(parsed[0]))
            if (tried_but_missed or ignored_protocol) \
                    and round_no < rounds - 1 and not retried_json:
                retried_json = True
                answer = ""
                why = ("not valid blocks JSON" if tried_but_missed
                       else "not in the blocks JSON format")
                note("warn", f"The answer was {why} — asking once more.")
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content":
                                 f"Your final answer was {why}. Send it again as ONE line, "
                                 "exactly: FINAL: {\"blocks\":[...]} — using only the block "
                                 "shapes from the instructions. No ###, no markdown tables, "
                                 "no other text on that line. Summarise the files in your own "
                                 "words; do not paste long raw text from them into the answer."})
                continue
            note("done", "Answer ready.")
            break
        name, args = action
        note("tool", f"Calling {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
        tool_span = obs.tool_call(name, args, description=_tool_description(name))
        result = run_tool(name, args, folder)
        obs.finish_tool(tool_span, result, ok=not result.startswith("Unknown tool"))
        call = ToolCall(name=name, args=args, result=result)
        calls.append(call)
        used_tools = True
        note("tool-done", result.splitlines()[0] if result else f"{name} returned nothing")
        if name == "read_file":
            path = str(args.get("path") or "")
            if path and path not in used_files:
                used_files.append(path)
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user",
                         "content": f"Tool result:\n{result}\n\n"
                                    "Continue: call another tool, or give the final answer "
                                    "(last line: FINAL: {\"blocks\":[...]})."})
    # The model may still be asking for tools when the rounds run out. Ask it
    # for the answer explicitly, so the user is never left with a tool call.
    if not answer and calls:
        note("work", "Asking the model to answer with what it has.")
        messages.append({"role": "user",
                         "content": "Give the final answer now, using what you have found. "
                                    "Do not call any more tools. Last line: FINAL: {\"blocks\":[...]}"})
        try:
            res = client.chat(messages, system=system)
            answer = strip_tool_calls((res.text or "").strip())
            if answer:
                note("done", "Answer ready.")
            else:
                note("warn", "The model did not give an answer.")
        except Exception as e:  # noqa: BLE001
            note("warn", f"The final answer failed: {e}")
    result = AgentResult(answer=answer, calls=calls,
                          used_tools=bool(calls), files=used_files)
    if answer:
        result.raw = answer
        result.answer, result.blocks, _, _ = structured_answer(answer)
        result.citations = _citations(folder, used_files)
    obs.finish_agent(run_span, blocks_to_text(result.blocks) or result.answer)
    return result


def _clean_final(text: str) -> str:
    """Tidy the answer: the FINAL: line is a protocol marker, not content."""
    body = text
    final = ""
    if "FINAL:" in text:
        body, _, final = text.partition("FINAL:")
    body = body.strip()
    final = final.strip()
    if body:
        return body
    return final or text.strip()


def parse_ai_lines(text: str) -> tuple[str, list[str], list["Proposal"]]:
    """Split the model's answer from its organisation lines.

    A trailing block of ``RENAME:``, ``MOVE:`` and ``GAP:`` lines is not prose:
    the renames become Review proposals the user approves (nothing moves on
    its own), and the gaps become notes about what the folder is missing.
    """
    text = re.sub(r"^\s*FINAL:\s*", "", text.strip())
    prose: list[str] = []
    gaps: list[str] = []
    props: list[Proposal] = []
    for raw in text.splitlines():
        line = raw.strip()
        m_move = re.match(r"^(?:RENAME|MOVE):\s*(.+?)\s*->\s*(.+?)\s*$", line)
        m_gap = re.match(r"^GAP:\s*(.+)$", line)
        if m_gap:
            gaps.append(m_gap.group(1))
            continue
        if m_move:
            src = m_move.group(1).strip().strip('"')
            dst = m_move.group(2).strip().strip('"')
            if dst.endswith("/"):
                # A directory target: the file keeps its name, just moves in.
                props.append(Proposal(source=src, dest_dir=dst.rstrip("/") + "/",
                                      new_name=pathlib.PureWindowsPath(src).name if "\\" in src
                                      else pathlib.Path(src).name,
                                      reason=f"belongs together in {dst.rstrip('/')}",
                                      confidence=0.6, origin="llm"))
            else:
                # A file target beside the source: a rename in place.
                props.append(Proposal(source=src, dest_dir="",
                                      new_name=dst.rsplit("/", 1)[-1],
                                      reason="clearer name proposed by the model",
                                      confidence=0.6, origin="llm"))
            continue
        prose.append(raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(prose)).strip()
    return cleaned, gaps, props


# --- the answer protocol ----------------------------------------------------
# The model answers in a strict format: FINAL: {"blocks":[...]}. The blocks
# are validated with Pydantic, so the UI renders typed content it can trust
# and raw markdown can never leak into the answer, whatever the model writes.
class HeadingBlock(BaseModel):
    type: Literal["heading"]
    level: int = 1
    text: str


class ParaBlock(BaseModel):
    type: Literal["p"]
    text: str


class ListBlock(BaseModel):
    type: Literal["list"]
    items: list[str]


class TableBlock(BaseModel):
    type: Literal["table"]
    columns: list[str] = []
    rows: list[list[str]] = []


class FactItem(BaseModel):
    label: str
    value: str


class FactsBlock(BaseModel):
    type: Literal["facts"]
    entries: list[FactItem]


Block = HeadingBlock | ParaBlock | ListBlock | TableBlock | FactsBlock

_HASH = re.compile(r"^#{1,6}\s*")


def _clean_block_text(text: str) -> str:
    """No markdown artifacts survive into a block's text."""
    lines = [_HASH.sub("", line).replace("**", "") for line in text.splitlines()]
    return "\n".join(lines).strip()


def _validate_blocks(raw: object) -> list[dict] | None:
    """The model's blocks list, validated — or None if it does not conform."""
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    try:
        for item in raw:
            b = TypeAdapter(Block).validate_python(item)
            if b.type == "heading":
                out.append({"type": "heading",
                            "level": min(max(b.level, 1), 3),
                            "text": _clean_block_text(b.text)})
            elif b.type == "p":
                out.append({"type": "p", "text": _clean_block_text(b.text)})
            elif b.type == "list":
                out.append({"type": "list",
                            "items": [_clean_block_text(i) for i in b.items]})
            elif b.type == "table":
                out.append({"type": "table",
                            "columns": [_clean_block_text(c) for c in b.columns],
                            "rows": [[_clean_block_text(c) for c in row]
                                     for row in b.rows]})
            else:
                out.append({"type": "facts",
                            "entries": [{"label": _clean_block_text(e.label),
                                         "value": _clean_block_text(e.value)}
                                        for e in b.entries]})
    except ValidationError:
        return None
    if not any(b.get("text") or b.get("items") or b.get("rows")
               or b.get("entries") for b in out):
        return None
    return out


def _scrub_artifacts(text: str) -> str:
    """Remove stray markdown artifact runs anywhere inside a line.

    Line-start hashes must be left for the heading converter; only runs that
    follow a space or dash mid-line — leftovers of a model that ignored the
    protocol, like 'document: ### Visible text' — are removed.
    """
    text = re.sub(r"(?<=[ \t])#{2,6}(\s+|$)", "", text)
    return text


def _markdown_to_blocks(text: str) -> list[dict]:
    """Convert a non-protocol answer (markdown-ish) into proper blocks.

    The model may ignore the JSON protocol; it famously still writes
    '#'-headings, '-' lists and '|' tables. Instead of dumping that raw
    (the literal '###' disaster), translate it into the same typed blocks
    the protocol produces, so the UI renders it cleanly either way.
    """
    blocks: list[dict] = []
    lines = _scrub_artifacts(text).splitlines()
    para: list[str] = []
    items: list[str] = []
    cols: list[str] | None = None
    rows: list[list[str]] = []

    def flush_para() -> None:
        if para:
            blocks.append({"type": "p", "text": " ".join(x.strip() for x in para).strip()})
            para.clear()

    def flush_list() -> None:
        if items:
            blocks.append({"type": "list", "items": items[:12]})
            items.clear()

    def flush_table() -> None:
        nonlocal cols, rows
        if cols:
            blocks.append({"type": "table", "columns": cols, "rows": rows[:30]})
            cols, rows = None, []

    for line in lines:
        stripped = line.strip()
        m_head = re.match(r"^#{1,6}\s*(.*)$", stripped)
        if m_head:
            flush_para(); flush_list(); flush_table()
            n = len(stripped) - len(stripped.lstrip("#"))
            level = 1 if n <= 2 else 2 if n == 3 else 3
            blocks.append({"type": "heading", "level": level,
                           "text": m_head.group(1).replace("**", "").strip()})
            continue
        # Models write section titles as fully bolded lines ("**Summary**").
        m_bold = re.match(r"^\*\*([^*]+)\*\*$", stripped)
        if m_bold:
            flush_para(); flush_list(); flush_table()
            blocks.append({"type": "heading", "level": 2, "text": m_bold.group(1).strip()})
            continue
        if cols is None and re.match(r"^[-*]\s+", stripped):
            flush_para()
            items.append(_clean_block_text(stripped[2:]))
            continue
        if cols is None and re.match(r"^\d+\.\s+", stripped):
            flush_para()
            items.append(_clean_block_text(re.sub(r"^\d+\.\s+", "", stripped)))
            continue
        if re.match(r"^(\|.+\|)\s*$", stripped):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cols is None:
                if re.match(r"^[\s:|-]+$", stripped) and len(cells) >= 1:
                    cols = ["col%d" % i for i in range(len(cells))]
                else:
                    cols = [_clean_block_text(c) for c in cells]
            elif re.match(r"^[\s:|-]+$", stripped):
                continue  # the |---| separator row
            else:
                rows.append([_clean_block_text(c) for c in cells[:len(cols)]])
            continue
        if cols is not None and stripped:
            rows.append([_clean_block_text(c) for c in stripped.split("|")[:len(cols)]])
            continue
        flush_list(); flush_table()
        if not stripped:
            flush_para()
            continue
        para.append(stripped)
    flush_para(); flush_list(); flush_table()
    return blocks


def _fallback_blocks(text: str) -> list[dict]:
    """A non-protocol answer, still rendered properly: markdown-ish text is
    converted to typed blocks — never a raw dump with literal '###'."""
    return _markdown_to_blocks(text)


def _answer_needs_format_retry(text: str) -> bool:
    """True when the model clearly wrote block-level markdown instead of
    following the JSON protocol — one corrective round is worth it."""
    if '"blocks"' in text:
        return False  # it tried; the retry branch elsewhere handles misses
    first = text.lstrip()[:400]
    return bool(re.match(r"^#{1,6}\s", first)
                or re.match(r"^\|.+\|", first, re.M)
                or re.search(r"(?m)^#{1,6}\s", first)
                or re.search(r"(?m)^\|\s*-{2,}", first))


def blocks_to_text(blocks: list[dict]) -> str:
    """The answer as plain text (citation detection, logs, tests)."""
    parts: list[str] = []
    for b in blocks:
        if b["type"] == "heading":
            parts.append(b["text"])
        elif b["type"] == "p":
            parts.append(b["text"])
        elif b["type"] == "list":
            parts.extend(b["items"])
        elif b["type"] == "table":
            parts.extend(" | ".join(r) for r in b["rows"])
        elif b["type"] == "facts":
            parts.extend(f"{e['label']}: {e['value']}" for e in b["entries"])
    return "\n\n".join(p for p in parts if p)


def structured_answer(text: str) -> tuple[str, list[dict], list[str], list[Proposal]]:
    """Parse the final answer once, in one place.

    The FINAL line may carry the strict blocks JSON; the lines after it may
    carry RENAME/MOVE/GAP organisation lines. Anything the model got wrong
    degrades to clean plain-text blocks — never to raw markdown in the UI.
    """
    text = re.sub(r"^\s*FINAL:\s*", "", text.strip())
    blocks: list[dict] | None = None
    remainder = text
    start = text.find("{")
    if start >= 0:
        try:
            obj, end = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict):
                blocks = _validate_blocks(obj.get("blocks"))
                if blocks is not None:
                    remainder = (text[:start] + text[start + end:]).strip()
        except ValueError:
            blocks = None  # fall through to the plain-text path below
    org_text, gaps, props = parse_ai_lines(remainder)
    if blocks is None:
        blocks = _fallback_blocks(org_text)
        clean = re.sub(r"\n{3,}", "\n\n", blocks_to_text(blocks)).strip()
    else:
        clean = blocks_to_text(blocks)
    return clean, blocks, gaps, props


def _citations(folder: str | pathlib.Path, files: list[str]) -> list[Citation]:
    """Cite the files the agent actually read."""
    out: list[Citation] = []
    for path in files:
        rows = [c for c in index_db.chunks(folder) if c[0] == path]
        for _, page, text in rows[:2]:
            out.append(Citation(path, page, text[:300]))
    return out
