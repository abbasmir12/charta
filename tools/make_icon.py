"""Generate charta/assets/charta.ico — a real multi-size icon, stdlib only.

The mark is the logo gradient (#7C5CFF → #22D3EE) on a rounded square with a
white diamond glyph, drawn at 16/24/32/48/64/128/256 px and packed into one
.ico so Windows can pick the right size for the title bar, alt-tab, taskbar and
Explorer. No Pillow, no CDN, no build step: run `python3 tools/make_icon.py`.

    python3 tools/make_icon.py [output.ico]
"""
from __future__ import annotations

import pathlib
import struct
import sys
import zlib

SIZES = (16, 24, 32, 48, 64, 128, 256)
ACCENT1 = (0x7C, 0x5C, 0xFF)
ACCENT2 = (0x22, 0xD3, 0xEE)
GLYPH = (0xFF, 0xFF, 0xFF)
DEFAULT_OUT = pathlib.Path(__file__).resolve().parent.parent / "charta" / "assets" / "charta.ico"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _rounded_rect_sdf(px: float, py: float, size: float, radius: float) -> float:
    """Signed distance to a rounded square (negative = inside)."""
    half = size / 2.0
    dx = abs(px - half) - (half - radius)
    dy = abs(py - half) - (half - radius)
    outside = (max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) ** 0.5
    return outside + min(max(dx, dy), 0.0) - radius


def _diamond_sdf(px: float, py: float, size: float, half: float) -> float:
    """Signed distance to a diamond (|dx| + |dy| == half)."""
    return abs(px - size / 2.0) + abs(py - size / 2.0) - half


def render_rgba(size: int) -> bytes:
    """One size, raw RGBA rows (no PNG framing yet)."""
    radius = size * 0.22
    diamond_half = size * 0.30
    stroke = max(1.4, size * 0.055)
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter byte: none
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            cover = _clamp(0.5 - _rounded_rect_sdf(px, py, size, radius))
            t = _clamp((x + y) / (2.0 * max(1, size - 1)))
            # 1px inner highlight at the top, echoing the glass surfaces in DESIGN.md
            edge = _clamp(1.0 - max(0.0, 1.5 + _rounded_rect_sdf(px, py, size, radius)))
            color = [ACCENT1[i] + (ACCENT2[i] - ACCENT1[i]) * t for i in range(3)]
            color = [min(255.0, c + 40.0 * edge * 0.25) for c in color]
            glyph = _clamp(1.0 - abs(_diamond_sdf(px, py, size, diamond_half)) / (stroke / 2.0))
            if glyph > 0:
                for i in range(3):
                    color[i] = color[i] * (1 - glyph) + GLYPH[i] * glyph
            alpha = int(round(255 * cover))
            rows += bytes((int(round(color[0])), int(round(color[1])),
                           int(round(color[2])), alpha))
    return bytes(rows)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_png(size: int, rgba: bytes) -> bytes:
    """Minimal PNG encoder (8-bit RGBA, no interlace).

    ``rgba`` already carries one filter byte per row (see ``render_rgba``).
    """
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(rgba, 9)) + _chunk(b"IEND", b""))


def encode_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """ICO container with PNG-compressed entries (Vista+)."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def build_ico(sizes: tuple[int, ...] = SIZES) -> bytes:
    return encode_ico([(s, encode_png(s, render_rgba(s))) for s in sizes])


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    data = build_ico()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes, sizes: {', '.join(map(str, SIZES))})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
