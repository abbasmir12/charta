import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from charta.core.charter import create_charter_from_text, preset_charter, load_charter, save_charter


def test_presets(tmp_path):
    for name in ("student", "freelancer", "data_entry"):
        ch = preset_charter(name)
        assert ch.purpose
        p = save_charter(tmp_path, ch)
        assert p.exists()
        back = load_charter(tmp_path)
        assert back is not None and back.purpose == ch.purpose
        assert back.fields == ch.fields


def test_create_fallback_no_client():
    ch = create_charter_from_text("receipts and invoices I track for taxes", None)
    assert "receipt" in ch.purpose.lower() or ch.preset == "freelancer"
    md = ch.to_markdown()
    assert "---" in md and "Purpose" in md
