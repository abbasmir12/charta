"""Metadata for a file: what it is, what is inside it, and the fields in it.

The metadata is what the AI reads first: instead of re-analysing a folder file
by file, Charta describes every file once (type, vendor, date, amount, tags)
and keeps that description in the index. The model then works from the
metadata of the few files that matter.

Descriptions are deterministic (regexes on the text and the file name) so the
index is cheap to build and never invents anything; the model is only asked
for a summary when one is really wanted.
"""
from __future__ import annotations

import pathlib
import re
from collections import Counter

from .ask import _amounts, _dates, _date_parts, _doc_types, _vendor, describe_file, tokens

# Words too common to be useful as tags.
_COMMON = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "are",
    "was", "were", "have", "has", "had", "not", "but", "all", "can", "will",
    "would", "there", "their", "they", "them", "its", "our", "out", "about",
    "into", "over", "than", "then", "them", "these", "those", "what", "when",
    "which", "while", "who", "how", "why", "been", "being", "more", "most",
    "some", "such", "only", "other", "same", "very", "also", "just", "like",
    "invoice", "receipt", "document", "file", "total", "date", "amount",
}


def extract_metadata(rel: str, text: str, *, pages: int = 0,
                     method: str = "") -> dict:
    """Everything Charta knows about one file, without guessing."""
    name = pathlib.Path(rel).name
    kind_set = _doc_types(f"{name} {text[:400]}")
    kind = sorted(kind_set)[0] if kind_set else "document"
    vendor = _vendor(name)
    dates = _dates(text + " " + name)
    amounts = _amounts(text)
    months, years = _date_parts(text + " " + name)

    fields: dict[str, str] = {}
    if dates:
        fields["date"] = dates[0]
    if vendor:
        fields["vendor"] = vendor
    if amounts:
        fields["amount"] = amounts[0]
        fields["currency"] = re.sub(r"[\d.,\s]", "", amounts[0]) or ""
    if kind:
        fields["category"] = kind

    tags: list[str] = []
    for tag in (kind, vendor, *sorted(years), *(str(m) for m in sorted(months))):
        if tag and tag not in tags:
            tags.append(tag)
    # The most distinctive words in the text: what a person would tag it with.
    counter = Counter(t for t in tokens(text) if len(t) > 3 and t not in _COMMON)
    for word, _count in counter.most_common(6):
        if word not in tags:
            tags.append(word)

    return {
        "description": describe_file(rel, text),
        "doc_type": kind,
        "tags": tags[:12],
        "fields": fields,
        "pages": pages,
        "method": method,
    }
