"""Purpose-driven outputs: receipts / study / data-entry."""
from __future__ import annotations

import csv
import pathlib
import re


def _read_text_files(folder: pathlib.Path) -> list[tuple[str, str]]:
    out = []
    for p in sorted(folder.rglob("*")):
        if ".charta" in p.parts or not p.is_file():
            continue
        if p.suffix.lower() in (".txt", ".md", ".csv"):
            try:
                out.append((str(p.relative_to(folder)), p.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                pass
    return out


AMOUNT_RX = re.compile(r"(?i)(total|amount|sum|\$|€|£)?\s*([$€£]?)\s*(\d+(?:[.,]\d{2}))")
DATE_RX = re.compile(r"(20\d\d[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d\d)")


def build_receipts(folder: str | pathlib.Path, out_dir: str | pathlib.Path | None = None) -> dict:
    folder = pathlib.Path(folder)
    dest = pathlib.Path(out_dir or (folder / ".charta" / "outputs"))
    dest.mkdir(parents=True, exist_ok=True)
    rows = [{"date": "", "vendor": "", "amount": "", "currency": "", "category": "", "source_file": ""}]
    rows = []
    for rel, text in _read_text_files(folder):
        name = pathlib.Path(rel).name
        vendor = re.split(r"[_\-.]", name)[0] if "_" in name or "-" in name else name.rsplit(".", 1)[0]
        m_amt = AMOUNT_RX.search(text)
        m_date = DATE_RX.search(text + " " + name)
        rows.append({
            "date": m_date.group(0) if m_date else "",
            "vendor": vendor,
            "amount": m_amt.group(3) if m_amt else "",
            "currency": m_amt.group(2) if m_amt and m_amt.group(2) else "",
            "category": "invoice" if "invoice" in (name + text).lower() else "receipt",
            "source_file": rel,
        })
    # also include non-text files as rows (pdf/image) with filename-derived info
    seen = {r["source_file"] for r in rows}
    for p in sorted(folder.rglob("*")):
        if ".charta" in p.parts or not p.is_file():
            continue
        rel = str(p.relative_to(folder))
        if rel in seen or p.suffix.lower() in (".xlsx", ".csv"):
            continue
        if ".charta/outputs" in rel:
            continue
        rows.append({"date": DATE_RX.search(rel).group(0) if DATE_RX.search(rel) else "",
                     "vendor": p.stem.split("_")[0], "amount": "", "currency": "",
                     "category": "invoice" if "invoice" in rel.lower() else "receipt",
                     "source_file": rel})
    csv_path = dest / "receipts.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "vendor", "amount", "currency", "category", "source_file"])
        w.writeheader()
        w.writerows(rows)
    xlsx_path = dest / "receipts.xlsx"
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Receipts"
        ws.append(["date", "vendor", "amount", "currency", "category", "source_file"])
        for r in rows:
            ws.append([r["date"], r["vendor"], r["amount"], r["currency"], r["category"], r["source_file"]])
        wb.save(xlsx_path)
    except ImportError:
        xlsx_path = csv_path
    return {"rows": len(rows), "csv": str(csv_path), "xlsx": str(xlsx_path)}


def build_study(folder: str | pathlib.Path, out_dir: str | pathlib.Path | None = None) -> dict:
    folder = pathlib.Path(folder)
    dest = pathlib.Path(out_dir or (folder / ".charta" / "outputs"))
    dest.mkdir(parents=True, exist_ok=True)
    files = _read_text_files(folder)
    subjects: dict[str, list[str]] = {}
    for rel, text in files:
        subj = pathlib.Path(rel).parent.name if len(pathlib.Path(rel).parts) > 1 else "General"
        subjects.setdefault(subj, []).append(f"## {rel}\n\n{text[:2000]}")
    notes_path = dest / "notes.md"
    notes_path.write_text("# Study Notes\n\n" + "\n\n".join(
        f"# {s}\n\n" + "\n\n".join(c) for s, c in subjects.items()) or "# Study Notes\n\n(empty)",
        encoding="utf-8")
    flash_path = dest / "flashcards.csv"
    with open(flash_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["front", "back", "source"])
        for rel, text in files:
            first = next((l.strip() for l in text.splitlines() if l.strip()), rel)
            w.writerow([f"What is the key point of {rel}?", first[:200], rel])
    return {"notes": str(notes_path), "flashcards": str(flash_path), "subjects": sorted(subjects)}


def build_data_entry(folder: str | pathlib.Path, fields: list[str],
                     out_dir: str | pathlib.Path | None = None) -> dict:
    folder = pathlib.Path(folder)
    dest = pathlib.Path(out_dir or (folder / ".charta" / "outputs"))
    dest.mkdir(parents=True, exist_ok=True)
    fields = fields or ["name", "phone", "amount"]
    rows = []
    for rel, text in _read_text_files(folder):
        row = {"source_file": rel}
        for fld in fields:
            m = re.search(rf"(?i){re.escape(fld)}\s*[:=]\s*(.+)", text)
            row[fld] = m.group(1).strip()[:200] if m else ""
        rows.append(row)
    # include binary files as empty rows so nothing is lost
    seen = {r["source_file"] for r in rows}
    for p in sorted(folder.rglob("*")):
        if ".charta" in p.parts or not p.is_file():
            continue
        rel = str(p.relative_to(folder))
        if rel not in seen and ".charta/outputs" not in rel and p.suffix.lower() not in (".xlsx", ".csv"):
            rows.append({"source_file": rel, **{f: "" for f in fields}})
    csv_path = dest / "data_entry.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source_file", *fields])
        w.writeheader()
        w.writerows(rows)
    return {"rows": len(rows), "csv": str(csv_path), "fields": fields}
