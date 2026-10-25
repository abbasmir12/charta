"""Generate charta/assets/charta.ico (+ a 64px PNG) from chartalogo.png.

Stdlib only: decodes the source PNG (RGBA/RGB, 8-bit), bilinearly
downsamples to every icon size, and packs them into one multi-size .ico so
Windows can pick the right size for the title bar, alt-tab, taskbar and
Explorer. Re-run after replacing chartalogo.png:

    python3 tools/make_icon.py
"""
from __future__ import annotations

import pathlib
import struct
import sys
import zlib

SIZES = (16, 24, 32, 48, 64, 128, 256)
DEFAULT_OUT = pathlib.Path(__file__).resolve().parent.parent / "charta" / "assets" / "charta.ico"
DEFAULT_PNG = pathlib.Path(__file__).resolve().parent.parent / "charta" / "assets" / "charta.png"
SOURCE = pathlib.Path(__file__).resolve().parent.parent / "chartalogo.png"


def _decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Decode an 8-bit RGB/RGBA (or grayscale) PNG into RGBA bytes."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, _inter = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8:
                raise ValueError(f"unsupported bit depth {bit_depth}")
            if _inter != 0:
                raise ValueError("interlaced PNGs are not supported")
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break
    if not width or not height:
        raise ValueError("missing IHDR")
    raw = zlib.decompress(bytes(idat))
    channels = {0: 1, 2: 3, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"unsupported color type {color_type}")
    stride = width * channels
    # Unfilter each scanline (filter types 0..4).
    prev = bytearray(stride)
    out = bytearray(height * stride)
    i = 0
    for y in range(height):
        ftype = raw[i]
        i += 1
        row = bytearray(raw[i:i + stride])
        i += stride
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = prev[x]
            ul = prev[x - channels] if x >= channels else 0
            val = row[x]
            if ftype == 0:
                pass
            elif ftype == 1:
                val = (val + left) & 0xFF
            elif ftype == 2:
                val = (val + up) & 0xFF
            elif ftype == 3:
                val = (val + ((left + up) // 2)) & 0xFF
            elif ftype == 4:
                a_, b_, c_ = left, up, ul
                p_ = a_ + b_ - c_
                pa, pb, pc = abs(p_ - a_), abs(p_ - b_), abs(p_ - c_)
                pred = a_ if pa <= pb and pa <= pc else (b_ if pb <= pc else c_)
                val = (val + pred) & 0xFF
            else:
                raise ValueError(f"unknown filter {ftype}")
            row[x] = val
        out[y * stride:(y + 1) * stride] = row
        prev = row
    # Promote to RGBA.
    if channels == 4:
        return width, height, bytes(out)
    if channels == 3:
        rgba = bytearray(width * height * 4)
        for i in range(width * height):
            rgba[i * 4] = out[i * 3]
            rgba[i * 4 + 1] = out[i * 3 + 1]
            rgba[i * 4 + 2] = out[i * 3 + 2]
            rgba[i * 4 + 3] = 255
        return width, height, bytes(rgba)
    # grayscale
    rgba = bytearray(width * height * 4)
    for i in range(width * height):
        v = out[i]
        rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = v
        rgba[i * 4 + 3] = 255
    return width, height, bytes(rgba)


def _bilinear(src: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    """Bilinear resize of an RGBA buffer."""
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        sy = (y + 0.5) * sh / dh - 0.5
        y0 = int(sy)
        if y0 < 0:
            y0 = 0
        y1 = y0 + 1
        if y1 >= sh:
            y1 = sh - 1
        fy = sy - y0
        if fy < 0:
            fy = 0
        for x in range(dw):
            sx = (x + 0.5) * sw / dw - 0.5
            x0 = int(sx)
            if x0 < 0:
                x0 = 0
            x1 = x0 + 1
            if x1 >= sw:
                x1 = sw - 1
            fx = sx - x0
            if fx < 0:
                fx = 0
            def px(x, y):
                off = (y * sw + x) * 4
                return src[off:off + 4]
            p00 = px(x0, y0); p10 = px(x1, y0)
            p01 = px(x0, y1); p11 = px(x1, y1)
            for c in range(4):
                v = (p00[c] * (1 - fx) * (1 - fy) + p10[c] * fx * (1 - fy)
                     + p01[c] * (1 - fx) * fy + p11[c] * fx * fy)
                out[(y * dw + x) * 4 + c] = int(round(v))
    return bytes(out)


def _to_png_rows(rgba: bytes, size: int) -> bytes:
    """Add one filter byte (none) per scanline for the PNG encoder."""
    row = size * 4
    out = bytearray()
    for y in range(size):
        out.append(0)
        out += rgba[y * row:(y + 1) * row]
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_png(size: int, rgba: bytes) -> bytes:
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(_to_png_rows(rgba, size), 9))
            + _chunk(b"IEND", b""))


def encode_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def build(source: pathlib.Path) -> tuple[bytes, bytes]:
    """Return (ico_bytes, png64_bytes)."""
    sw, sh, rgba = _decode_png(source.read_bytes())
    pngs = []
    for s in SIZES:
        resized = _bilinear(rgba, sw, sh, s, s)
        pngs.append((s, encode_png(s, resized)))
    # 64px PNG for the in-app brand mark
    mark = _bilinear(rgba, sw, sh, 64, 64)
    mark_png = encode_png(64, mark)
    return encode_ico(pngs), mark_png


def build_ico() -> bytes:
    """Back-compat shim: ico bytes for the default source (used by tests)."""
    ico, _ = build(SOURCE)
    return ico


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    png_out = pathlib.Path(argv[2]) if len(argv) > 2 else DEFAULT_PNG
    if not SOURCE.exists():
        print(f"source not found: {SOURCE}", file=sys.stderr)
        return 1
    ico, png = build(SOURCE)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(ico)
    png_out.parent.mkdir(parents=True, exist_ok=True)
    png_out.write_bytes(png)
    print(f"wrote {out} ({len(ico)} bytes, sizes: {', '.join(map(str, SIZES))})")
    print(f"wrote {png_out} ({len(png)} bytes, 64x64)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
