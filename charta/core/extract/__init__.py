"""Single text-extraction interface. Swappable backends."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass


@dataclass
class ExtractResult:
    text: str
    pages: int = 1
    method: str = "none"


def extract_text(path: str | pathlib.Path) -> ExtractResult:
    p = pathlib.Path(path)
    suf = p.suffix.lower()
    try:
        if suf in (".txt", ".md", ".csv", ".json", ".toml", ".yaml", ".yml"):
            return ExtractResult(p.read_text(encoding="utf-8", errors="replace")[:20000], 1, "text")
        if suf == ".pdf":
            return _extract_pdf(p)
        if suf == ".docx":
            return _extract_docx(p)
        if suf in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"):
            return ExtractResult(f"[image file: {p.name}]", 1, "image-stub")
        return ExtractResult(f"[unsupported: {p.name}]", 1, "stub")
    except FileNotFoundError:
        return ExtractResult("", 0, "missing")
    except Exception as e:  # noqa: BLE001
        return ExtractResult(f"[extract-error: {e}]", 1, "error")


def _extract_pdf(p: pathlib.Path) -> ExtractResult:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(p)
        chunks = []
        for page in doc:
            chunks.append(page.get_text())
        text = "\n".join(chunks)[:30000]
        n = len(doc)
        doc.close()
        if text.strip():
            return ExtractResult(text, n, "pymupdf")
        return ExtractResult(f"[scanned pdf, {n} page(s): {p.name} — needs vision model]", n, "vision-needed")
    except ImportError:
        return ExtractResult(f"[pdf without PyMuPDF installed: {p.name}]", 1, "missing-dep")
    except Exception as e:  # noqa: BLE001
        return ExtractResult(f"[pdf-error: {e}]", 1, "error")


def _extract_docx(p: pathlib.Path) -> ExtractResult:
    try:
        import docx  # python-docx

        doc = docx.Document(str(p))
        return ExtractResult("\n".join(par.text for par in doc.paragraphs)[:20000], 1, "docx")
    except ImportError:
        return ExtractResult(f"[docx without python-docx: {p.name}]", 1, "missing-dep")
    except Exception as e:  # noqa: BLE001
        return ExtractResult(f"[docx-error: {e}]", 1, "error")
