"""Classification: Gemma proposes dest+name+reason; heuristic fallback."""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass

from .charter import Charter
from .llm import OllamaClient


@dataclass
class Proposal:
    source: str
    dest_dir: str
    new_name: str
    reason: str
    confidence: float = 0.7
    sensitive: bool = False
    status: str = "pending"


def _heuristic(text: str, filename: str, charter: Charter) -> Proposal:
    fn = filename.lower()
    tx = (text or "").lower()
    preset = ""
    p = charter.purpose.lower()
    if any(k in p for k in ("receipt", "invoice", "tax", "bill")):
        preset = "freelancer"
    elif any(k in p for k in ("data entry", "form")):
        preset = "data_entry"
    else:
        preset = "student"
    if preset == "freelancer":
        if "invoice" in fn or "invoice" in tx:
            dest = "Invoices"
        elif "statement" in fn:
            dest = "Statements"
        else:
            dest = "Receipts"
        m = re.search(r"(20\d\d[-_./]\d{1,2}[-_./]\d{1,2}|\d{1,2}[-_./]\d{1,2}[-_./]20\d\d)", fn + " " + tx)
        date = m.group(1).replace("/", "-").replace(".", "-") if m else "undated"
        reason = f"it looks like a {'invoice' if dest=='Invoices' else 'receipt'} ({date}) for your freelance taxes"
        return Proposal(filename, dest, filename, f"moved because {reason}", 0.62)
    if preset == "data_entry":
        return Proposal(filename, "Forms", filename,
                        "moved because it looks like a data-entry form to extract name, phone, amount from", 0.6)
    # student
    m = re.search(r"(lecture|lec|week|ch)[ _-]?(\d{1,2})", fn)
    if m:
        n = m.group(2)
        return Proposal(filename, "Lectures", filename,
                        f"moved because it is lecture material (lecture {n})", 0.66)
    if "assign" in fn:
        return Proposal(filename, "Assignments", filename,
                        "moved because it looks like an assignment", 0.64)
    if fn.endswith((".png", ".jpg", ".jpeg")):
        return Proposal(filename, "Screenshots", filename,
                        "moved because it is a study screenshot", 0.6)
    return Proposal(filename, "Notes", filename,
                    "moved because it looks like study material", 0.5)


def propose_for_file(filename: str, text: str, charter: Charter,
                     client: OllamaClient | None = None,
                     sensitive: bool = False) -> Proposal:
    if client is not None:
        prompt = ("Reply ONLY JSON {dest_dir,new_name,reason,confidence}. "
                  f"Charter purpose: {charter.purpose}. Structure: {json.dumps(charter.structure)}. "
                  f"File: {filename}. Content excerpt: {(text or '')[:1500]}")
        res = client.generate(prompt, system="Strict JSON only.", json_mode=True)
        if res.ok:
            try:
                raw = res.text[res.text.find("{"):res.text.rfind("}") + 1]
                d = json.loads(raw)
                return Proposal(filename, str(d.get("dest_dir", "Inbox")),
                                str(d.get("new_name", filename)),
                                str(d.get("reason", "suggested by local model")),
                                float(d.get("confidence", 0.7)), sensitive)
            except Exception:
                pass
    # retry once inside client already; fallback:
    prop = _heuristic(text, filename, charter)
    prop.sensitive = sensitive
    return prop
