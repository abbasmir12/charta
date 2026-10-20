"""Native window polish: guarded no-ops off Windows, plus geometry + icon parsing."""
from __future__ import annotations

import importlib.util
import pathlib
import struct

import charta.shell.native_window as nw

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _make_icon_module():
    spec = importlib.util.spec_from_file_location("_charta_make_icon", ROOT / "tools" / "make_icon.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_dwm_calls_are_safe_noops_off_windows():
    """On Linux/macOS every native call must return False, not raise."""
    for call in (nw.apply_dark_titlebar, nw.apply_rounded_corners):
        assert call(0) is False
    assert nw.apply_backdrop(0, nw.BACKDROP_MICA) is False
    assert nw.apply_solid_caption(0) is False
    assert nw.set_app_user_model_id() is False
    assert nw.set_window_icon(0, pathlib.Path("/nope/charta.ico")) is False
    report = nw.polish_window(0, ico_path=pathlib.Path("/nope/charta.ico"))
    assert report == {"dark_titlebar": False, "rounded_corners": False, "backdrop": False,
                      "app_user_model_id": False, "icon": False}


def test_geometry_round_trip(tmp_path):
    geo = nw.WindowGeometry(x=120, y=64, width=1440, height=900, maximized=True)
    path = nw.save_geometry(tmp_path, geo)
    assert path.exists() and path.name == "window.json"
    assert nw.load_geometry(tmp_path) == geo


def test_geometry_defaults_when_missing_or_corrupt(tmp_path):
    assert nw.load_geometry(tmp_path) == nw.WindowGeometry()
    nw.geometry_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert nw.load_geometry(tmp_path).width == 1180
    # a window too small to be usable falls back instead of opening invisibly
    nw.save_geometry(tmp_path, nw.WindowGeometry(width=10, height=10))
    assert nw.load_geometry(tmp_path).is_usable()


def test_icon_has_every_size_and_is_a_real_ico():
    data = _make_icon_module().build_ico()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    assert count == 7
    sizes = []
    for i in range(count):
        width, height, _c, _r, planes, bpp, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        sizes.append(width or 256)
        assert (planes, bpp) == (1, 32)
        entry = data[offset:offset + size]
        assert entry.startswith(b"\x89PNG\r\n\x1a\n")
        got_w, got_h = struct.unpack(">II", entry[16:24])
        assert (got_w, got_h) == (width or 256, height or 256)
    assert sizes == [16, 24, 32, 48, 64, 128, 256]


def test_shipped_icon_is_the_real_artifact():
    """The committed .ico must match the generator, not be an empty placeholder."""
    path = ROOT / "charta" / "assets" / "charta.ico"
    assert path.exists(), "run tools/make_icon.py"
    assert path.read_bytes() == _make_icon_module().build_ico()
