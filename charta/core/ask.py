"""Ask the folder: lexical retrieval + regex-aware intent, then a cited answer.

No embeddings, no vector database. Ranking combines BM25 over keywords with
cheap, explainable signals that matter for documents:

- a human description per chunk (doc type, vendor, date, amount)
- filename matches
- exact phrase / bigram matches
- month, year, number and amount matching
- document-type intent ("which invoice…")
- a small domain synonym table ("electricity" → EDF/power/kWh)

Regexes extract dates, months and amounts so "what did EDF charge in March?"
works even when the question and the receipt share few words. The configured
model is used only once, at the end, to write the answer from the best chunks.
"""
from __future__ import annotations

import math
import pathlib
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from . import sensitive as sens_mod
from .extract import VisionFn, extract_text
from .llm import LLMClient


@dataclass
class Citation:
    file: str
    page: int
    excerpt: str


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    found: bool


STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "from", "by", "with",
    "and", "or", "is", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "what", "which", "who", "whom", "when", "where", "why", "how", "much",
    "many", "this", "that", "these", "those", "it", "its", "i", "you", "we",
    "they", "my", "your", "our", "their", "me", "us", "them", "please", "show",
    "tell", "find", "give", "list", "all", "any", "there", "here", "about",
    "into", "over", "under", "again", "then", "than", "so", "such", "can",
    "could", "should", "would", "will", "shall", "may", "might", "must", "have",
    "has", "had",
}

SYNONYMS: dict[str, tuple[str, ...]] = {
    "electricity": ("edf", "power", "energy", "kwh", "bill", "utility"),
    "edf": ("electricity", "power", "energy"),
    "internet": ("broadband", "wifi", "box", "isp", "free"),
    "free": ("internet", "broadband", "wifi"),
    "rent": ("housing", "landlord", "lease", "apartment"),
    "housing": ("rent", "landlord", "apartment"),
    "travel": ("sncf", "train", "ticket", "trip", "rail"),
    "sncf": ("travel", "train", "ticket", "rail"),
    "tax": ("taxes", "expense", "deductible", "vat"),
    "bill": ("invoice", "receipt", "statement", "charge"),
    "invoice": ("bill", "receipt"),
    "receipt": ("bill", "invoice", "purchase"),
    "charge": ("amount", "total", "cost", "price", "paid"),
    "cost": ("amount", "total", "charge", "price"),
    "amount": ("total", "charge", "cost", "price"),
    "total": ("amount", "charge", "cost"),
    "phone": ("mobile", "telecom", "landline"),
    "lecture": ("class", "course", "slides", "lec"),
    "assignment": ("homework", "due", "deadline"),
    "form": ("data", "entry", "fields"),
}

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

DATE_RX = re.compile(
    r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b"
    r"|\b(\d{1,2})[-/.](\d{1,2})[-/.]?(20\d{2})\b")
AMOUNT_RX = re.compile(
    r"[€$£]\s?\d[\d.,]*"
    r"|\b(?:total|amount|sum|charge|paid|balance|cost|price)\s*[:=]?\s*"
    r"(?:[€$£]\s?)?\d[\d.,]*", re.I)
DOC_TYPES = {
    "receipt": re.compile(r"\breceipts?\b", re.I),
    "invoice": re.compile(r"\binvoices?\b", re.I),
    "statement": re.compile(r"\bstatements?\b", re.I),
    "form": re.compile(r"\bforms?\b", re.I),
    "lecture": re.compile(r"\blectures?\b|\blec\b", re.I),
    "assignment": re.compile(r"\bassignments?\b|\bhomework\b", re.I),
    "notes": re.compile(r"\bnotes?\b", re.I),
}


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def _stem(word: str) -> str:
    """Conservative plural folding; enough for keyword matching, no stemmer dep."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(t) for t in raw if t not in STOPWORDS and len(t) > 1]


def _expand(query_tokens: list[str]) -> list[str]:
    out = set(query_tokens)
    for t in list(query_tokens):
        out.update(SYNONYMS.get(t, ()))
    return sorted(out)


def _dates(text: str) -> list[str]:
    out = []
    for m in DATE_RX.finditer(text):
        if m.group(1):
            out.append(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
        elif m.group(6):
            a, b = int(m.group(4)), int(m.group(5))
            month, day = (b, a) if a > 12 else (a, b)
            out.append(f"{m.group(6)}-{month:02d}-{day:02d}")
    return out


def _date_parts(text: str) -> tuple[set[int], set[str]]:
    months: set[int] = set()
    years: set[str] = set()
    lower = text.lower()
    for name, num in MONTHS.items():
        if re.search(rf"\b{name}\b", lower):
            months.add(num)
    for d in _dates(text):
        years.add(d[:4])
        months.add(int(d[5:7]))
    years.update(re.findall(r"\b20\d{2}\b", text))
    return months, years


def _amounts(text: str) -> list[str]:
    vals = []
    for m in AMOUNT_RX.finditer(text):
        num = re.sub(r"[^\d.,]", "", m.group(0))
        if num:
            vals.append(num.replace(",", "."))
    return vals


def _doc_types(text: str) -> set[str]:
    text = re.sub(r"[_\-.]", " ", text)
    return {name for name, rx in DOC_TYPES.items() if rx.search(text)}


def _vendor(filename: str) -> str:
    skip = {"receipt", "invoice", "statement", "bank", "tax", "scan", "lecture",
            "form", "assignment", "notes", "doc", "document", "file", "img"}
    for part in re.split(r"[_\-\s.]+", pathlib.Path(filename).stem.lower()):
        if part and part not in skip and not re.fullmatch(r"\d+", part):
            if not re.fullmatch(r"20\d{2}", part):
                return part
    return ""


def describe_file(rel: str, text: str) -> str:
    """A deterministic one-line description used for ranking and citations."""
    name = pathlib.Path(rel).name
    kinds = _doc_types(name)
    kind = sorted(kinds)[0] if kinds else "document"
    vendor = _vendor(name)
    dates = _dates(text + " " + name)
    amounts = _amounts(text)
    bits = [kind]
    if vendor:
        bits.append(f"from {vendor}")
    if dates:
        bits.append(f"dated {dates[0]}")
    if amounts:
        bits.append(f"amount {amounts[0]}")
    return ", ".join(bits)


@dataclass
class Intent:
    raw: str
    terms: list[str]
    expanded: list[str]
    phrases: list[str]
    months: set[int] = field(default_factory=set)
    years: set[str] = field(default_factory=set)
    numbers: set[str] = field(default_factory=set)
    amounts: list[str] = field(default_factory=list)
    doc_types: set[str] = field(default_factory=set)
    wants_amount: bool = False
    wants_date: bool = False


def parse_intent(query: str) -> Intent:
    terms = tokens(query)
    low = (query or "").lower()
    months, years = _date_parts(query)
    numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", query))
    wants_amount = bool(re.search(
        r"how much|cost|charge|price|total|amount|paid|spent|€|\$|£|euro|dollar|pound",
        low))
    wants_date = bool(re.search(r"when|date|month|day|year|latest|recent|deadline", low))
    phrases = [" ".join(terms[i:i + 2]) for i in range(len(terms) - 1)]
    return Intent(raw=query, terms=terms, expanded=_expand(terms), phrases=phrases,
                  months=months, years=years, numbers=numbers,
                  amounts=_amounts(query), doc_types=_doc_types(query),
                  wants_amount=wants_amount, wants_date=wants_date)


def _idf(n: int, df: int) -> float:
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def _bm25(query_terms: list[str], doc_terms: list[str], df: Counter,
          n: int, avgdl: float, k1: float = 1.5, b: float = 0.75) -> float:
    tf = Counter(doc_terms)
    score = 0.0
    dl = len(doc_terms) or 1
    for term in set(query_terms):
        if not tf.get(term):
            continue
        score += _idf(n, df.get(term, 0)) * (
            tf[term] * (k1 + 1)) / (tf[term] + k1 * (1 - b + b * dl / (avgdl or 1)))
    return score


def build_index(folder: str | pathlib.Path,
                exclude_sensitive: bool = True,
                vision: VisionFn | None = None,
                max_files: int = 200,
                budget_seconds: float = 45.0,
                stats: dict | None = None,
                prefer_index: bool = True) -> list[dict]:
    """The retrieval index for a folder.

    The folder's own index (``.charta/index.db``) is used when it is up to
    date — that is the point of it: the files were read once, and every
    question afterwards works from their metadata and text instead of reading
    the folder again. When the index has nothing, the files are read now (and
    the index is filled in for next time).

    ``max_files`` and ``budget_seconds`` bound the work: a folder with
    thousands of files (or a big pile of images, each one a slow vision call)
    must not turn one question into a coffee break. ``stats`` is filled in with
    what was found and what was left out.
    """
    if not str(folder).strip():
        return []
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        return []
    if prefer_index:
        cached = index_from_db(folder, exclude_sensitive=exclude_sensitive)
        if cached:
            if stats is not None:
                stats.update({"files": len({d["file"] for d in cached}),
                              "indexed": len(cached), "truncated": False,
                              "seconds": 0.0, "source": "index"})
            return cached
    started = time.monotonic()
    index: list[dict] = []
    seen = 0
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or ".charta" in p.parts:
            continue
        if p.suffix.lower() not in (".txt", ".md", ".csv", ".pdf", ".docx",
                                    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"):
            continue
        seen += 1
        if len(index) >= max_files:
            break
        if time.monotonic() - started > budget_seconds:
            break
        res = extract_text(p, vision)
        if res.method == "image-stub":  # no vision model: nothing text-like to index
            continue
        if exclude_sensitive and sens_mod.detect(res.text).sensitive:
            continue
        rel = str(p.relative_to(folder))
        _remember(folder, rel, res, chunk_text(res.text), sensitive=False)
        for j, chunk in enumerate(chunk_text(res.text)):
            index.append(_doc(rel, j + 1, chunk))
    if stats is not None:
        stats.update({"files": seen, "indexed": len(index),
                      "truncated": seen > len(index),
                      "seconds": round(time.monotonic() - started, 2),
                      "source": "files"})
    return index


def _remember(folder: pathlib.Path, rel: str, res: object, chunks: list[str],
              sensitive: bool = False) -> None:
    """Keep what we just read in the folder's index (so we never read it twice)."""
    try:
        from . import index_db
        from .meta import extract_metadata  # local import: meta imports this module

        text = getattr(res, "text", "") or ""
        metadata = extract_metadata(rel, text, pages=int(getattr(res, "pages", 0) or 0),
                                   method=str(getattr(res, "method", "") or ""))
        index_db.upsert(folder, rel, text, metadata,
                        pages=int(getattr(res, "pages", 0) or 0),
                        method=str(getattr(res, "method", "") or ""),
                        sensitive=sensitive, chunks=chunks)
    except Exception:  # noqa: BLE001 — the index is a convenience, never a blocker
        return


def _doc(rel: str, page: int, chunk: str) -> dict:
    """One searchable document (a chunk of a file with its signals)."""
    desc = describe_file(rel, chunk)
    months, years = _date_parts(chunk + " " + rel)
    return {
        "file": rel, "page": page, "text": chunk, "desc": desc,
        "tokens": tokens(f"{rel} {desc} {chunk}"),
        "months": months, "years": years,
        "dates": _dates(chunk), "amounts": _amounts(chunk),
        "numbers": set(re.findall(r"\b\d+\b", chunk)),
        "types": _doc_types(f"{rel} {chunk}"),
    }


def index_from_db(folder: str | pathlib.Path, exclude_sensitive: bool = True) -> list[dict]:
    """The retrieval index built from the folder's stored chunks (no reading)."""
    from . import index_db  # local import: index_db must not depend on this module

    try:
        rows = index_db.chunks(folder)
        meta = index_db.file_meta(folder)
    except Exception:  # noqa: BLE001 — a missing or broken index is not fatal
        return []
    if not rows:
        return []
    out: list[dict] = []
    for rel, page, text in rows:
        if exclude_sensitive and meta.get(rel, {}).get("sensitive"):
            continue
        out.append(_doc(rel, page, text))
    return out


def index_signature(folder: str | pathlib.Path) -> str:
    """A cheap fingerprint of a folder: changes when its files do.

    Used to keep the Ask index in memory and rebuild it only when something
    actually changed, so the second question is instant.
    """
    root = pathlib.Path(folder)
    if not root.is_dir():
        return ""
    files = 0
    newest = 0.0
    total = 0
    for p in root.rglob("*"):
        if not p.is_file() or ".charta" in p.parts:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        files += 1
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return f"{files}:{total}:{newest:.3f}"


def _score(intent: Intent, doc: dict, df: Counter, n: int, avgdl: float) -> float:
    score = _bm25(intent.expanded, doc["tokens"], df, n, avgdl)
    text = doc["text"].lower()
    name = pathlib.Path(doc["file"]).name.lower()
    for phrase in intent.phrases:
        if phrase and (phrase in text or phrase in name):
            score += 2.5
    doc_terms = set(doc["tokens"])
    wanted = set(intent.expanded)
    score += 1.5 * len(wanted & set(tokens(doc["file"])))
    score += 1.0 * len(wanted & set(tokens(doc["desc"])))
    if intent.doc_types & doc["types"]:
        score += 2.0
    if intent.months & doc["months"]:
        score += 3.0
    if intent.years & doc["years"]:
        score += 1.5
    if intent.wants_amount and doc["amounts"]:
        score += 1.5
    if intent.amounts and set(intent.amounts) & set(doc["amounts"]):
        score += 2.0
    if intent.numbers & doc["numbers"]:
        score += 2.0
    if intent.wants_date and doc["dates"]:
        score += 1.0
    return score


def answer_query(query: str, index: list[dict], client: LLMClient | None = None,
                 top_k: int = 3, steps: list[dict] | None = None) -> Answer:
    """Answer a question from the index.

    ``steps`` collects what happened (ranked, model called, answered) so the UI
    can show the work instead of a spinner.
    """
    def note(kind: str, text: str) -> None:
        if steps is not None:
            steps.append({"kind": kind, "text": text})

    if not index:
        note("warn", "This folder has nothing indexed yet.")
        return Answer("I couldn't find that in this folder — no indexed files yet.", [], False)
    intent = parse_intent(query)
    if not intent.expanded:
        note("warn", "Nothing in the question to look for.")
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    df: Counter = Counter()
    for doc in index:
        df.update(set(doc["tokens"]))
    avgdl = sum(len(d["tokens"]) for d in index) / len(index)
    ranked = sorted(((_score(intent, d, df, len(index), avgdl), d) for d in index),
                    key=lambda pair: pair[0], reverse=True)
    best_score, best = ranked[0]
    if best_score <= 0:
        note("warn", "No file in the index matched those words.")
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    wanted = set(intent.terms)
    coverage = len(wanted & set(best["tokens"])) / max(1, len(wanted))
    if coverage < 0.25 and not (intent.months or intent.amounts or intent.numbers):
        note("warn", "The closest file does not really match the question.")
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    top = [doc for _, doc in ranked[:top_k]]
    cites = [Citation(r["file"], r["page"], r["text"][:300]) for r in top]
    note("work", f"Matched {len(top)} file(s): "
                + ", ".join(sorted({c.file for c in cites})))
    context = "\n\n".join(
        f"[{c.file} p{c.page}] ({d['desc']})\n{c.excerpt}" for c, d in zip(cites, top))
    if client:
        note("model", f"Asking {client.cfg.llm_provider}/{client.cfg.generation_model}…")
        res = client.generate(
            "Answer ONLY from this folder context. Cite [file pN]. Keep exact "
            "dates and amounts. If the context does not contain the answer, say so.\n"
            f"Q: {query}\nContext:\n{context}", system="Be concise and factual.")
        # A model that has learned to call tools may answer this prompt with a
        # tool call. That is not an answer — fall back to the matched text.
        from .agent import strip_tool_calls
        text = strip_tool_calls(res.text or "") if res.ok else ""
        if text:
            note("done", "Answer ready.")
            return Answer(text, cites, True)
        if res.ok:
            note("warn", "The model answered with a tool call — showing the matched text instead.")
        else:
            note("warn", "The model did not answer — showing the matched text instead.")
    best = top[0]
    note("done", "Answer ready (from the index).")
    return Answer(f"Based on {best['file']} (p{best['page']}) — {best['desc']}: "
                  f"{best['text'][:500]}", cites, True)
