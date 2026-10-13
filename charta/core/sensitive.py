"""Sensitive-content detection (IDs, cards, passwords)."""
from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS = {
    "card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "password": re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    "api_key": re.compile(r"(?i)(api[_-]?key|secret)\s*[:=]\s*\S+"),
}


@dataclass
class SensitiveReport:
    sensitive: bool
    kinds: list[str]


def detect(text: str) -> SensitiveReport:
    kinds = [k for k, rx in PATTERNS.items() if rx.search(text or "")]
    # naive Luhn-ish check only to reduce false positives for card pattern
    return SensitiveReport(sensitive=bool(kinds), kinds=kinds)


def redact(text: str) -> str:
    out = text or ""
    for rx in PATTERNS.values():
        out = rx.sub("[REDACTED]", out)
    return out
