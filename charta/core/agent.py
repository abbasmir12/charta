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
from dataclasses import dataclass, field

from . import index_db
from .ask import Citation, chunk_text
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
4. When you can answer, write it in plain language and cite the file and page
   like [receipt_edf.txt p1]. Never invent a fact. If the folder does not
   contain the answer, say so plainly.
5. The last line of your final answer must be exactly:
   FINAL: <your answer>

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
            return f"read_file: '{path}' is not in the index."
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
                   steps: list[dict] | None = None, rounds: int = MAX_ROUNDS) -> AgentResult:
    """Let the model use the folder's tools, then answer.

    Falls back to a plain answer when the model does not call any tool.
    """
    def note(kind: str, text: str) -> None:
        if steps is not None:
            steps.append({"kind": kind, "text": text})

    tool_text = "\n".join(f"- {t['name']}({', '.join(t['parameters']) or 'no arguments'}): "
                          f"{t['description']}" for t in TOOL_SPECS)
    system = SYSTEM.format(tools=tool_text, catalogue=catalogue(folder))
    note("work", "Showing the model the index catalogue.")
    messages: list[dict] = [{"role": "user", "content": question}]
    calls: list[ToolCall] = []
    used_files: list[str] = []
    answer = ""
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
            answer = text
            note("done", "Answer ready.")
            break
        name, args = action
        note("tool", f"Calling {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
        result = run_tool(name, args, folder)
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
                                    "(last line: FINAL: <your answer>)."})
    result = AgentResult(answer=answer, calls=calls,
                          used_tools=bool(calls), files=used_files)
    if answer:
        result.answer = _clean_final(answer)
        result.citations = _citations(folder, used_files)
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


def _citations(folder: str | pathlib.Path, files: list[str]) -> list[Citation]:
    """Cite the files the agent actually read."""
    out: list[Citation] = []
    for path in files:
        rows = [c for c in index_db.chunks(folder) if c[0] == path]
        for _, page, text in rows[:2]:
            out.append(Citation(path, page, text[:300]))
    return out
