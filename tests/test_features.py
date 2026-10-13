from charta.core.ask import answer_query, build_index, chunk_text, hash_embed
from charta.core.charter import preset_charter
from charta.core.gaps import find_gaps
from charta.core.outputs import build_data_entry, build_receipts, build_study


def test_receipts_output(tmp_path):
    (tmp_path / "receipt_edf_2026-03-15.txt").write_text("date: 2026-03-15\ntotal: $42.00\n")
    out = build_receipts(tmp_path)
    assert out["rows"] >= 1
    assert (tmp_path / ".charta" / "outputs" / "receipts.csv").exists()


def test_study_output(tmp_path):
    (tmp_path / "lecture_01.txt").write_text("Intro to OS\nKey point: processes.")
    out = build_study(tmp_path)
    assert "notes" in out
    import pathlib

    assert pathlib.Path(out["flashcards"]).exists()


def test_data_entry_output(tmp_path):
    (tmp_path / "form_001.txt").write_text("name: Alice\nphone: 0600\namount: 99\n")
    out = build_data_entry(tmp_path, ["name", "phone", "amount"])
    assert out["rows"] >= 1


def test_gaps():
    gaps = find_gaps(["lecture 1..3 slides"], ["lecture_01.txt", "lecture_03.txt"])
    missing = [g for g in gaps if not g.found]
    assert any("2" in g.expected for g in missing)


def test_ask_citations_and_refusal(tmp_path):
    (tmp_path / "lecture_01.txt").write_text("photosynthesis happens in chloroplasts of plants")
    idx = build_index(tmp_path, None)
    assert idx
    ans = answer_query("photosynthesis", idx, None)
    assert ans.found and ans.citations and "lecture_01" in ans.citations[0].file
    no = answer_query("quantum gravity zebra", idx, None)
    assert not no.found and "couldn't find" in no.text


def test_chunk_and_embed():
    assert chunk_text("") == []
    v = hash_embed("hello world")
    assert abs(sum(x * x for x in v) - 1.0) < 1e-6
