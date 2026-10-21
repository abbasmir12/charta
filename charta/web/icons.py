"""Inline Lucide icons (ISC) — bundled, no CDN (DESIGN.md §1).

`svg()` emits one icon at the caller's size with `currentColor`, so the
whole UI shares a single icon language. Path data is inlined from
lucide-static v1.59.0; regenerate with tools/fetch_icons.py if it grows.
"""
from __future__ import annotations

import json

_PATHS: dict[str, str] = {
    "overview": "<rect width=\"7\" height=\"9\" x=\"3\" y=\"3\" rx=\"1\" /><rect width=\"7\" height=\"5\" x=\"14\" y=\"3\" rx=\"1\" /><rect width=\"7\" height=\"9\" x=\"14\" y=\"12\" rx=\"1\" /><rect width=\"7\" height=\"5\" x=\"3\" y=\"16\" rx=\"1\" />",
    "review": "<path d=\"M13 5h8\" /><path d=\"M13 12h8\" /><path d=\"M13 19h8\" /><path d=\"m3 17 2 2 4-4\" /><path d=\"m3 7 2 2 4-4\" />",
    "outputs": "<path d=\"M3 9h18\" /><path d=\"M9 3v18\" /><rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"2\" />",
    "gaps": "<circle cx=\"12\" cy=\"12\" r=\"10\" /><circle cx=\"12\" cy=\"12\" r=\"6\" /><circle cx=\"12\" cy=\"12\" r=\"2\" />",
    "ask": "<path d=\"M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z\" /><path d=\"M7 11h10\" /><path d=\"M7 15h6\" /><path d=\"M7 7h8\" />",
    "activity": "<path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\" /><path d=\"M3 3v5h5\" /><path d=\"M12 7v5l4 2\" />",
    "settings": "<path d=\"M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915\" /><circle cx=\"12\" cy=\"12\" r=\"3\" />",
    "folder": "<path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\" />",
    "folder-add": "<path d=\"M12 10v6\" /><path d=\"M9 13h6\" /><path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\" />",
    "sun": "<circle cx=\"12\" cy=\"12\" r=\"4\" /><path d=\"M12 2v2\" /><path d=\"M12 20v2\" /><path d=\"m4.93 4.93 1.41 1.41\" /><path d=\"m17.66 17.66 1.41 1.41\" /><path d=\"M2 12h2\" /><path d=\"M20 12h2\" /><path d=\"m6.34 17.66-1.41 1.41\" /><path d=\"m19.07 4.93-1.41 1.41\" />",
    "moon": "<path d=\"M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401\" />",
    "mic": "<path d=\"M12 19v3\" /><path d=\"M19 10v2a7 7 0 0 1-14 0v-2\" /><rect x=\"9\" y=\"2\" width=\"6\" height=\"13\" rx=\"3\" />",
    "plus": "<path d=\"M5 12h14\" /><path d=\"M12 5v14\" />",
    "arrow-right": "<path d=\"M5 12h14\" /><path d=\"m12 5 7 7-7 7\" />",
    "chevron-right": "<path d=\"m9 18 6-6-6-6\" />",
    "chevron-down": "<path d=\"m6 9 6 6 6-6\" />",
    "shield": "<path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\" /><path d=\"m9 12 2 2 4-4\" />",
    "file": "<path d=\"M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z\" /><path d=\"M14 2v5a1 1 0 0 0 1 1h5\" /><path d=\"M10 9H8\" /><path d=\"M16 13H8\" /><path d=\"M16 17H8\" />",
    "undo": "<path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\" /><path d=\"M3 3v5h5\" />",
    "search": "<path d=\"m21 21-4.34-4.34\" /><circle cx=\"11\" cy=\"11\" r=\"8\" />",
    "alert": "<path d=\"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3\" /><path d=\"M12 9v4\" /><path d=\"M12 17h.01\" />",
    "drive": "<path d=\"M10 16h.01\" /><path d=\"M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z\" /><path d=\"M21.946 12.013H2.054\" /><path d=\"M6 16h.01\" />",
    "info": "<circle cx=\"12\" cy=\"12\" r=\"10\" /><path d=\"M12 16v-4\" /><path d=\"M12 8h.01\" />",
    "tree": "<path d=\"M20 10a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-2.5a1 1 0 0 1-.8-.4l-.9-1.2A1 1 0 0 0 15 3h-2a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1Z\" /><path d=\"M20 21a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1h-2.9a1 1 0 0 1-.88-.55l-.42-.85a1 1 0 0 0-.92-.6H13a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1Z\" /><path d=\"M3 5a2 2 0 0 0 2 2h3\" /><path d=\"M3 3v13a2 2 0 0 0 2 2h3\" />",
    "empty": "<path d=\"M10.1 2.182a10 10 0 0 1 3.8 0\" /><path d=\"M13.9 21.818a10 10 0 0 1-3.8 0\" /><path d=\"M17.609 3.721a10 10 0 0 1 2.69 2.7\" /><path d=\"M2.182 13.9a10 10 0 0 1 0-3.8\" /><path d=\"M20.279 17.609a10 10 0 0 1-2.7 2.69\" /><path d=\"M21.818 10.1a10 10 0 0 1 0 3.8\" /><path d=\"M3.721 6.391a10 10 0 0 1 2.7-2.69\" /><path d=\"M6.391 20.279a10 10 0 0 1-2.69-2.7\" />",
    "check": "<path d=\"M20 6 9 17l-5-5\" />",
    "close": "<path d=\"M18 6 6 18\" /><path d=\"m6 6 12 12\" />",
    "sparkles": "<path d=\"M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z\" /><path d=\"M20 2v4\" /><path d=\"M22 4h-4\" /><circle cx=\"4\" cy=\"20\" r=\"2\" />",
    "play": "<path d=\"M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z\" />",
    "scan": "<path d=\"M3 7V5a2 2 0 0 1 2-2h2\" /><path d=\"M17 3h2a2 2 0 0 1 2 2v2\" /><path d=\"M21 17v2a2 2 0 0 1-2 2h-2\" /><path d=\"M7 21H5a2 2 0 0 1-2-2v-2\" /><path d=\"M7 12h10\" />",
    "stack": "<path d=\"M4 10c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h4c1.1 0 2 .9 2 2\" /><path d=\"M10 16c-1.1 0-2-.9-2-2v-4c0-1.1.9-2 2-2h4c1.1 0 2 .9 2 2\" /><rect width=\"8\" height=\"8\" x=\"14\" y=\"14\" rx=\"2\" />",
    "sort": "<path d=\"m7 15 5 5 5-5\" /><path d=\"m7 9 5-5 5 5\" />",
    "folders": "<path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\" /><path d=\"M18 9h-8a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-10a2 2 0 0 0-2-2Z\" />",
    "files": "<path d=\"M20 7h-3a2 2 0 0 1-2-2V2\" /><path d=\"M9 18a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h7l5 5v9a2 2 0 0 1-2 2Z\" /><path d=\"M3 7.6v12.8A1.6 1.6 0 0 0 4.6 22h9.8\" />",
    "history": "<line x1=\"12\" x2=\"12\" y1=\"3\" y2=\"15\" /><line x1=\"3\" x2=\"21\" y1=\"9\" y2=\"9\" /><circle cx=\"12\" cy=\"15\" r=\"3\" /><circle cx=\"6\" cy=\"9\" r=\"3\" /><circle cx=\"18\" cy=\"9\" r=\"3\" />"
}

DEFAULT = "empty"


def svg(name: str, size: int = 18, stroke: float = 1.75, cls: str = "") -> str:
    """One inline icon; unknown names fall back to a neutral placeholder."""
    body = _PATHS.get(name, _PATHS[DEFAULT])
    klass = f' class="{cls}"' if cls else ""
    return (
        f'<svg{klass} viewBox="0 0 24 24" width="{size}" height="{size}" fill="none"'
        f' stroke="currentColor" stroke-width="{stroke}" stroke-linecap="round"'
        f' stroke-linejoin="round" aria-hidden="true">{body}</svg>')


def manifest() -> str:
    """Icon bodies as a JSON object, injected for client-side rendering."""
    return json.dumps(_PATHS)


__all__ = ["DEFAULT", "manifest", "svg"]
