"""Per-folder metadata index (SQLite, in the standard library).

Every file Charta reads gets a row: what it is, what is inside it, which
fields were found (date, vendor, amount), the tags, and the extracted text in
chunks. Two things read this index:

  * **Ask** — the retrieval step works on the index instead of re-reading
    every file for every question, so the second question is instant.
  * **Search** — a proper search over names, descriptions, tags and fields,
    with clickable results.

The database lives in the folder's own ``.charta/index.db``: it belongs to that
folder, travels with it, and is never inside the user's visible files.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sqlite3
from typing import Any

DB_NAME = "index.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path        TEXT PRIMARY KEY,
  name        TEXT,
  ext         TEXT,
  size        INTEGER DEFAULT 0,
  mtime       REAL DEFAULT 0,
  pages       INTEGER DEFAULT 0,
  chars       INTEGER DEFAULT 0,
  method      TEXT DEFAULT '',
  description TEXT DEFAULT '',
  doc_type    TEXT DEFAULT '',
  tags        TEXT DEFAULT '',
  fields      TEXT DEFAULT '{}',
  sensitive   INTEGER DEFAULT 0,
  indexed_at  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chunks (
  path  TEXT NOT NULL,
  page  INTEGER NOT NULL,
  text  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS files_type ON files(doc_type);
"""


def index_path(folder: str | pathlib.Path) -> pathlib.Path:
    """Where a folder's index lives."""
    return pathlib.Path(folder) / ".charta" / DB_NAME


def connect(folder: str | pathlib.Path) -> sqlite3.Connection:
    """Open (and create) the folder's index."""
    path = index_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(folder: str | pathlib.Path, rel: str, text: str, metadata: dict[str, Any],
           *, pages: int = 0, method: str = "", sensitive: bool = False,
           chunks: list[str] | None = None) -> None:
    """Record a file and its chunks. Re-indexing the same file replaces it."""
    path = pathlib.Path(folder) / rel
    try:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
    except OSError:
        size, mtime = 0, 0.0
    conn = connect(folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO files (path, name, ext, size, mtime, pages, chars,"
            " method, description, doc_type, tags, fields, sensitive, indexed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rel, pathlib.Path(rel).name, pathlib.Path(rel).suffix.lstrip(".").lower(),
             size, mtime, pages, len(text), method,
             str(metadata.get("description", "")), str(metadata.get("doc_type", "")),
             " ".join(metadata.get("tags", [])), json.dumps(metadata.get("fields", {})),
             1 if sensitive else 0,
             datetime.datetime.now().isoformat(timespec="seconds")))
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        if chunks is None:
            chunks = [text] if text else []
        conn.executemany("INSERT INTO chunks (path, page, text) VALUES (?,?,?)",
                         [(rel, i + 1, c) for i, c in enumerate(chunks)])
        conn.commit()
    finally:
        conn.close()


def remove(folder: str | pathlib.Path, rel: str) -> None:
    """Forget a file (it was moved away or trashed)."""
    conn = connect(folder)
    try:
        conn.execute("DELETE FROM files WHERE path = ?", (rel,))
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        conn.commit()
    finally:
        conn.close()


def files(folder: str | pathlib.Path) -> list[dict]:
    """Every indexed file, newest first."""
    conn = connect(folder)
    try:
        rows = conn.execute(
            "SELECT * FROM files ORDER BY indexed_at DESC, name").fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["fields"] = json.loads(item.get("fields") or "{}")
        except ValueError:
            item["fields"] = {}
        item["tags"] = [t for t in str(item.get("tags", "")).split() if t]
        item["sensitive"] = bool(item.get("sensitive"))
        out.append(item)
    return out


def chunks(folder: str | pathlib.Path) -> list[tuple[str, int, str]]:
    """Every chunk of every file: (path, page, text)."""
    conn = connect(folder)
    try:
        rows = conn.execute("SELECT path, page, text FROM chunks ORDER BY path, page").fetchall()
    finally:
        conn.close()
    return [(r["path"], int(r["page"]), r["text"]) for r in rows]


def file_meta(folder: str | pathlib.Path) -> dict[str, dict]:
    """path -> metadata row (description, tags, fields…)."""
    return {f["path"]: f for f in files(folder)}


def stats(folder: str | pathlib.Path) -> dict:
    """How much the index knows about this folder."""
    conn = connect(folder)
    try:
        files_n = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
        chunks_n = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        types = conn.execute(
            "SELECT doc_type, COUNT(*) AS n FROM files WHERE doc_type != ''"
            " GROUP BY doc_type ORDER BY n DESC").fetchall()
    finally:
        conn.close()
    return {"files": int(files_n), "chunks": int(chunks_n),
            "types": {r["doc_type"]: int(r["n"]) for r in types}}


def search(folder: str | pathlib.Path, query: str, limit: int = 50) -> list[dict]:
    """Search the index: name, tags, description, fields and the text itself.

    Results are ranked: a name match beats a tag match, which beats a hit in
    the description, which beats a hit buried in the text.
    """
    terms = [t for t in str(query or "").lower().split() if len(t) > 1]
    if not terms:
        return []
    conn = connect(folder)
    try:
        rows = conn.execute("SELECT * FROM files").fetchall()
        hits: dict[str, float] = {}
        matched: dict[str, set[str]] = {}
        for row in rows:
            rel = row["path"]
            score = 0.0
            why: set[str] = set()
            name = str(row["name"] or "").lower()
            tags = str(row["tags"] or "").lower()
            desc = str(row["description"] or "").lower()
            fields = str(row["fields"] or "").lower()
            for term in terms:
                if term in name:
                    score += 6.0
                    why.add("name")
                if term in tags:
                    score += 4.0
                    why.add("tag")
                if term in desc:
                    score += 3.0
                    why.add("description")
                if term in fields:
                    score += 2.5
                    why.add("field")
            if score:
                hits[rel] = score
                matched[rel] = why
        # The text itself is the last resort (and the slowest), so it only runs
        # for the files that did not already match by name or tag.
        for term in terms:
            for row in conn.execute(
                    "SELECT path FROM chunks WHERE lower(text) LIKE ? LIMIT 200", (f"%{term}%",)):
                rel = row["path"]
                if rel in hits:
                    hits[rel] += 0.5
                else:
                    hits[rel] = 0.5
                    matched[rel] = {"text"}
    finally:
        conn.close()
    if not hits:
        return []
    meta = {f["path"]: f for f in files(folder)}
    out = []
    for rel, score in hits.items():
        item = meta.get(rel)
        if not item:
            continue
        item = dict(item)
        item["score"] = round(score, 2)
        item["matched"] = sorted(matched.get(rel, ()))
        out.append(item)
    out.sort(key=lambda i: (-i["score"], i["name"]))
    return out[:limit]
