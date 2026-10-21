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
                vision: VisionFn | None = None) -> list[dict]:
    """Chunk every readable file and attach the signals used for ranking.

    An empty folder is refused: ``Path("")`` means "the current directory",
    which would silently index whatever the app happens to be sitting in.
    """
    if not str(folder).strip():
        return []
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        return []
    index: list[dict] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or ".charta" in p.parts:
            continue
        if p.suffix.lower() not in (".txt", ".md", ".csv", ".pdf", ".docx",
                                    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"):
            continue
        res = extract_text(p, vision)
        if res.method == "image-stub":  # no vision model: nothing text-like to index
            continue
        if exclude_sensitive and sens_mod.detect(res.text).sensitive:
            continue
        rel = str(p.relative_to(folder))
        for j, chunk in enumerate(chunk_text(res.text)):
            desc = describe_file(rel, chunk)
            months, years = _date_parts(chunk + " " + rel)
            index.append({
                "file": rel, "page": j + 1, "text": chunk, "desc": desc,
                "tokens": tokens(f"{rel} {desc} {chunk}"),
                "months": months, "years": years,
                "dates": _dates(chunk), "amounts": _amounts(chunk),
                "numbers": set(re.findall(r"\b\d+\b", chunk)),
                "types": _doc_types(f"{rel} {chunk}"),
            })
    return index


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
                 top_k: int = 3) -> Answer:
    if not index:
        return Answer("I couldn't find that in this folder — no indexed files yet.", [], False)
    intent = parse_intent(query)
    if not intent.expanded:
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    df: Counter = Counter()
    for doc in index:
        df.update(set(doc["tokens"]))
    avgdl = sum(len(d["tokens"]) for d in index) / len(index)
    ranked = sorted(((_score(intent, d, df, len(index), avgdl), d) for d in index),
                    key=lambda pair: pair[0], reverse=True)
    best_score, best = ranked[0]
    if best_score <= 0:
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    wanted = set(intent.terms)
    coverage = len(wanted & set(best["tokens"])) / max(1, len(wanted))
    if coverage < 0.25 and not (intent.months or intent.amounts or intent.numbers):
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)

    top = [doc for _, doc in ranked[:top_k]]
    cites = [Citation(r["file"], r["page"], r["text"][:300]) for r in top]
    context = "\n\n".join(
        f"[{c.file} p{c.page}] ({d['desc']})\n{c.excerpt}" for c, d in zip(cites, top))
    if client:
        res = client.generate(
            "Answer ONLY from this folder context. Cite [file pN]. Keep exact "
            "dates and amounts. If the context does not contain the answer, say so.\n"
            f"Q: {query}\nContext:\n{context}", system="Be concise and factual.")
        if res.ok and res.text.strip():
            return Answer(res.text.strip(), cites, True)
    best = top[0]
    return Answer(f"Based on {best['file']} (p{best['page']}) — {best['desc']}: "
                  f"{best['text'][:500]}", cites, True)
