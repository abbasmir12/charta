"""Ask the folder: chunk, embed (Ollama or hash fallback), cosine retrieve, cite."""
from __future__ import annotations

import hashlib
import math
import pathlib
import re
from dataclasses import dataclass

from . import sensitive as sens_mod
from .extract import extract_text
from .llm import OllamaClient


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


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim
        vec[h] += 1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def build_index(folder: str | pathlib.Path, client: OllamaClient | None = None,
                exclude_sensitive: bool = True) -> list[dict]:
    folder = pathlib.Path(folder)
    idx = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or ".charta" in p.parts:
            continue
        if p.suffix.lower() not in (".txt", ".md", ".csv", ".pdf", ".docx"):
            continue
        res = extract_text(p)
        if exclude_sensitive and sens_mod.detect(res.text).sensitive:
            continue
        for j, ch in enumerate(chunk_text(res.text)):
            emb = client.embed(ch) if client else None
            idx.append({"file": str(p.relative_to(folder)), "page": j + 1,
                        "text": ch, "emb": emb or hash_embed(ch)})
    return idx


def answer_query(query: str, index: list[dict], client: OllamaClient | None = None,
                 top_k: int = 3) -> Answer:
    if not index:
        return Answer("I couldn't find that in this folder — no indexed files yet.", [], False)
    q_emb = (client.embed(query) if client else None) or hash_embed(query)
    ranked = sorted(index, key=lambda d: cosine(q_emb, d["emb"]), reverse=True)[:top_k]
    if not ranked or cosine(q_emb, ranked[0]["emb"]) < 0.05:
        return Answer("I couldn't find that in this folder — nothing relevant matched.", [], False)
    cites = [Citation(r["file"], r["page"], r["text"][:300]) for r in ranked]
    context = "\n\n".join(f"[{c.file} p{c.page}] {c.excerpt}" for c in cites)
    if client:
        res = client.generate(
            f"Answer ONLY from this folder context. Cite [file pN]. If absent, say you couldn't find it.\n"
            f"Q: {query}\nContext:\n{context}")
        if res.ok and res.text.strip():
            return Answer(res.text.strip(), cites, True)
    # fallback extractive answer
    best = ranked[0]
    return Answer(f"Based on {best['file']} (p{best['page']}): {best['text'][:500]}", cites, True)
