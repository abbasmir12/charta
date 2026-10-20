"""Folder Charter: markdown + YAML front-matter, presets, LLM creation w/ fallback."""
from __future__ import annotations

import datetime
import json
import pathlib
import re
from dataclasses import asdict, dataclass, field

from .llm import LLMClient

CHARTER_FILENAME = ".charta/charter.md"

PRESETS: dict[str, dict] = {
    "student": {
        "purpose": "Lecture PDFs and study screenshots for my CS degree",
        "belongs": ["lecture slides (pdf)", "screenshots of whiteboards/code", "assignments", "study notes"],
        "structure": {"Lectures": "lecture_*", "Assignments": "assignment_*", "Notes": "*.md", "Screenshots": "*.png|*.jpg"},
        "fields": ["subject", "lecture_number", "topic"],
        "expected": ["lecture 1..12 slides", "assignments 1..4"],
        "flags": ["exam dates", "blurry screenshots"],
    },
    "freelancer": {
        "purpose": "Receipts and invoices I want to track for my freelance taxes",
        "belongs": ["receipts", "invoices (incoming + outgoing)", "bank statements"],
        "structure": {"Receipts": "receipt_*", "Invoices": "invoice_*", "Statements": "statement_*"},
        "fields": ["date", "vendor", "amount", "currency", "category", "source_file"],
        "expected": ["electricity bill for each month (Jan..Dec)", "rent receipts monthly"],
        "flags": ["amounts over 1000", "missing VAT numbers"],
    },
    "data_entry": {
        "purpose": "Data entry: extract name, phone, and amount from each form",
        "belongs": ["scanned forms (pdf/png)", "typed forms (docx/txt)"],
        "structure": {"Forms": "form_*", "Exports": "exports/"},
        "fields": ["name", "phone", "amount"],
        "expected": ["form batch A (1..50)"],
        "flags": ["missing phone", "unreadable scans"],
    },
}


@dataclass
class Charter:
    purpose: str
    belongs: list[str] = field(default_factory=list)
    structure: dict[str, str] = field(default_factory=dict)
    fields: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    learned_rules: list[str] = field(default_factory=list)
    mode: str = "suggest"
    preset: str = "custom"
    updated: str = ""

    def to_markdown(self) -> str:
        fm = {
            "preset": self.preset,
            "mode": self.mode,
            "fields": self.fields,
            "expected": self.expected,
            "structure": self.structure,
            "updated": self.updated or datetime.datetime.now().isoformat(timespec="seconds"),
        }
        lines = ["---"]
        for k, v in fm.items():
            lines.append(f"{k}: {json.dumps(v)}")
        lines += ["---", f"# Folder Charter", "", f"**Purpose:** {self.purpose}", "",
                  "## What belongs here"]
        lines += [f"- {b}" for b in self.belongs] or ["- (anything relevant)"]
        lines += ["", "## Folder structure rules"]
        lines += [f"- `{pat}` → `{dest}/`" for dest, pat in self.structure.items()] or ["- (flat)"]
        lines += ["", "## Fields to extract", ", ".join(f"`{f}`" for f in self.fields) or "(none)"]
        lines += ["", "## Expected items"]
        lines += [f"- [ ] {e}" for e in self.expected] or ["- (none declared)"]
        lines += ["", "## Things to flag"]
        lines += [f"- {f}" for f in self.flags] or ["- (none)"]
        lines += ["", "## Learned rules"]
        lines += [f"- {r}" for r in self.learned_rules] or ["- (none yet — approve corrections to teach me)"]
        return "\n".join(lines) + "\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Charter":
        fm: dict = {}
        body = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                fm_block = text[3:end].strip()
                body = text[end + 4:]
                for line in fm_block.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        try:
                            fm[k.strip()] = json.loads(v.strip())
                        except Exception:
                            fm[k.strip()] = v.strip().strip('"')
        purpose = ""
        m = re.search(r"\*\*Purpose:\*\*\s*(.+)", body)
        if m:
            purpose = m.group(1).strip()
        def section(name: str) -> list[str]:
            mm = re.search(rf"## {re.escape(name)}\n(.+?)(?=\n## |\Z)", body, re.S)
            if not mm:
                return []
            return [re.sub(r"^-\s*(\[[ x]\]\s*)?", "", l).strip("` ").strip() for l in mm.group(1).splitlines() if l.strip().startswith("-")]
        belongs = section("What belongs here")
        flags = section("Things to flag")
        expected = [e for e in section("Expected items")]
        learned = [l for l in section("Learned rules") if "none yet" not in l.lower()]
        structure: dict[str, str] = {}
        if isinstance(fm.get("structure"), dict):
            structure = dict(fm["structure"])
        return cls(
            purpose=purpose or str(fm.get("purpose", "")),
            belongs=belongs, structure=structure,
            fields=list(fm.get("fields", [])),
            expected=list(fm.get("expected", [])),
            flags=flags, learned_rules=learned,
            mode=str(fm.get("mode", "suggest")),
            preset=str(fm.get("preset", "custom")),
        )


def save_charter(folder: pathlib.Path, charter: Charter) -> pathlib.Path:
    dest = pathlib.Path(folder) / CHARTER_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(charter.to_markdown(), encoding="utf-8")
    return dest


def load_charter(folder: pathlib.Path) -> Charter | None:
    p = pathlib.Path(folder) / CHARTER_FILENAME
    if not p.exists():
        return None
    return Charter.from_markdown(p.read_text(encoding="utf-8"))


def preset_charter(name: str) -> Charter:
    d = PRESETS[name]
    return Charter(purpose=d["purpose"], belongs=list(d["belongs"]),
                   structure=dict(d["structure"]), fields=list(d["fields"]),
                   expected=list(d["expected"]), flags=list(d["flags"]), preset=name)


def _guess_preset(purpose: str) -> str:
    p = purpose.lower()
    if any(k in p for k in ("receipt", "invoice", "tax", "freelance", "expense", "bill")):
        return "freelancer"
    if any(k in p for k in ("lecture", "study", "student", "exam", "cs degree", "notes", "flashcard")):
        return "student"
    if any(k in p for k in ("data entry", "extract", "form", "name, phone")):
        return "data_entry"
    return "student"


def create_charter_from_text(purpose: str, client: LLMClient | None = None) -> Charter:
    """Ask Gemma for structured charter JSON; fallback to preset template."""
    base = preset_charter(_guess_preset(purpose))
    base.purpose = purpose.strip() or base.purpose
    if client is None:
        return base
    prompt = (
        "You turn a folder purpose into a folder charter. Reply ONLY valid JSON with keys: "
        'belongs (list of str), structure (obj dest->glob), fields (list), expected (list), flags (list). '
        f"Purpose: {purpose}"
    )
    res = client.generate(prompt, system="You output strict JSON only.", json_mode=True)
    if not res.ok:
        return base
    for attempt in range(2):
        try:
            data = json.loads(res.text[res.text.find("{"):res.text.rfind("}") + 1])
            if isinstance(data, dict):
                for k in ("belongs", "fields", "expected", "flags"):
                    if k in data and isinstance(data[k], list):
                        setattr(base, k, [str(x) for x in data[k]])
                if isinstance(data.get("structure"), dict):
                    base.structure = {str(k): str(v) for k, v in data["structure"].items()}
                return base
        except Exception:
            if attempt == 0:
                res = client.generate(prompt + "\nReturn ONLY JSON.", json_mode=True)
    return base
