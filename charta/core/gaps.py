"""Gap detection: expected-vs-found from charter."""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass


@dataclass
class Gap:
    expected: str
    found: bool
    note: str


def _expand_lecture_range(spec: str) -> list[str]:
    m = re.search(r"lecture\s+(\d+)\.\.(\d+)", spec, re.I)
    if m:
        return [f"lecture {i}" for i in range(int(m.group(1)), int(m.group(2)) + 1)]
    return [spec]


def find_gaps(expected: list[str], files: list[str]) -> list[Gap]:
    blob = "\n".join(files).lower()
    gaps: list[Gap] = []
    for spec in expected:
        for item in _expand_lecture_range(spec):
            # month-name check e.g. "electricity bill for march"
            mm = re.search(r"(?i)(january|february|march|april|may|june|july|august|september|october|november|december)", item)
            lm = re.search(r"(?i)lecture\s+(\d+)", item)
            found = False
            if lm:
                n = lm.group(1)
                found = bool(re.search(rf"(lecture|lec|week)[ _-]?0?{n}\b", blob))
                note = f"Lecture {n} slides not found" if not found else f"Lecture {n} present"
            elif mm:
                month = mm.group(1).lower()
                found = month[:3] in blob or month in blob
                note = f"No {item.strip()} found" if not found else f"{item.strip()} present"
            else:
                key = re.sub(r"\W+", " ", item).strip().lower()
                found = key[:12] in blob if len(key) > 12 else key in blob
                note = f"Missing: {item}" if not found else f"Found: {item}"
            gaps.append(Gap(item, found, note))
    return gaps


def gaps_for_folder(folder: str | pathlib.Path, expected: list[str]) -> list[Gap]:
    files = [str(p.relative_to(folder)) for p in pathlib.Path(folder).rglob("*")
             if p.is_file() and ".charta" not in p.parts]
    return find_gaps(expected, files)
