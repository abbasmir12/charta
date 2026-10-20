#!/usr/bin/env python3
"""Regenerate `charta/web/icons.py` from lucide-static.

The UI bundles its icons (no CDN, DESIGN.md §1), so the SVG bodies live in the
repo. Run this only when the icon set changes:

    python3 tools/fetch_icons.py

It needs network access to unpkg.com; the generated file is deterministic and
committed, so a normal checkout never touches the network.
"""
from __future__ import annotations

import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "charta" / "web" / "icons.py"
BASE = "https://unpkg.com/lucide-static@latest/icons/{slug}.svg"

# semantic name -> lucide slug. Keep the keys in sync with call sites.
ICONS = {
    "overview": "layout-dashboard", "review": "list-checks", "outputs": "table-2",
    "gaps": "target", "ask": "message-square-text", "activity": "history",
    "settings": "settings", "folder": "folder", "folder-add": "folder-plus",
    "sun": "sun", "moon": "moon", "mic": "mic", "plus": "plus",
    "arrow-right": "arrow-right", "chevron-right": "chevron-right",
    "shield": "shield-check", "file": "file-text", "undo": "rotate-ccw",
    "search": "search", "alert": "triangle-alert", "drive": "hard-drive",
    "info": "info", "tree": "folder-tree", "empty": "circle-dashed",
    "check": "check", "close": "x", "sparkles": "sparkles", "play": "play",
    "scan": "scan-line", "stack": "square-stack", "sort": "chevrons-up-down",
}


def fetch(slug: str) -> str:
    """The inner markup of one lucide icon, whitespace-normalised."""
    with urllib.request.urlopen(BASE.format(slug=slug), timeout=30) as resp:
        svg = resp.read().decode("utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1).strip()
    return re.sub(r"\s+", " ", re.sub(r">\s+<", "><", inner)).strip()


def build() -> str:
    paths = {name: fetch(slug) for name, slug in ICONS.items()}
    body = json.dumps(paths, indent=4, ensure_ascii=False)
    return (
        '"""Inline Lucide icons (ISC) — bundled, no CDN (DESIGN.md §1).\n\n'
        "`svg()` emits one icon at the caller's size with `currentColor`, so the\n"
        "whole UI shares a single icon language. Path data is inlined from\n"
        "lucide-static v1.59.0; regenerate with tools/fetch_icons.py if it grows.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "import json\n\n"
        f"_PATHS: dict[str, str] = {body}\n\n"
        'DEFAULT = "empty"\n\n\n'
        'def svg(name: str, size: int = 18, stroke: float = 1.75, cls: str = "") -> str:\n'
        '    """One inline icon; unknown names fall back to a neutral placeholder."""\n'
        "    body = _PATHS.get(name, _PATHS[DEFAULT])\n"
        "    klass = f' class=\"{cls}\"' if cls else \"\"\n"
        "    return (\n"
        "        f'<svg{klass} viewBox=\"0 0 24 24\" width=\"{size}\" height=\"{size}\" fill=\"none\"'\n"
        "        f' stroke=\"currentColor\" stroke-width=\"{stroke}\" stroke-linecap=\"round\"'\n"
        "        f' stroke-linejoin=\"round\" aria-hidden=\"true\">{body}</svg>')\n\n\n"
        'def manifest() -> str:\n'
        '    """Icon bodies as a JSON object, injected for client-side rendering."""\n'
        "    return json.dumps(_PATHS)\n\n\n"
        '__all__ = ["DEFAULT", "manifest", "svg"]\n'
    )


def main() -> int:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(ICONS)} icons)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
