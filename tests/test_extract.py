"""Extractor: text/PDF/docx unchanged; images go through the vision hook."""
from charta.core.extract import extract_many, extract_text


def test_image_without_vision_is_a_stub(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"x")
    res = extract_text(p)
    assert res.method == "image-stub" and "shot.png" in res.text


def test_image_with_vision_transcribes_and_redacts(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"x")
    res = extract_text(p, lambda data, mime: "card 4111 1111 1111 1111 total $5")
    assert res.method == "vision"
    assert "[REDACTED]" in res.text


def test_vision_failure_never_breaks_extraction(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"x")

    def boom(data: bytes, mime: str) -> str:
        raise RuntimeError("model offline")

    assert extract_text(p, boom).method == "image-stub"


def test_unsupported_and_missing_files(tmp_path):
    assert extract_text(tmp_path / "nope.txt").method == "missing"
    (tmp_path / "f.bin").write_bytes(b"x")
    assert extract_text(tmp_path / "f.bin").method == "stub"


def test_extract_many(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    results = extract_many([tmp_path / "a.txt", tmp_path / "b.txt"])
    assert [r.method for r in results] == ["text", "text"]
