from charta.core.ask import (answer_query, build_index, chunk_text, describe_file,
                             parse_intent)
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
    idx = build_index(tmp_path)
    assert idx
    ans = answer_query("photosynthesis", idx, None)
    assert ans.found and ans.citations and "lecture_01" in ans.citations[0].file
    no = answer_query("quantum gravity zebra", idx, None)
    assert not no.found and "found nothing matching" in no.text and "lecture_01.txt" in no.text


def test_ask_uses_dates_amounts_and_filename(tmp_path):
    (tmp_path / "receipt_edf_2026-03-14.txt").write_text(
        "receipt from EDF\ndate: 2026-03-14\ntotal: €87.40\ncategory: electricity")
    (tmp_path / "receipt_free_2026-03-01.txt").write_text(
        "receipt from Free\ndate: 2026-03-01\ntotal: €29.99\ncategory: internet")
    (tmp_path / "invoice_rent_2026-04-01.txt").write_text(
        "invoice from Rent\ndate: 2026-04-01\ntotal: €780.00\ncategory: housing")
    idx = build_index(tmp_path)
    ans = answer_query("what did EDF charge in March?", idx, None)
    assert ans.found
    assert "receipt_edf" in ans.citations[0].file
    assert "87.40" in ans.text
    electricity = answer_query("electricity bill", idx, None)
    assert "receipt_edf" in electricity.citations[0].file


def test_ask_doc_type_and_no_embeddings(tmp_path):
    (tmp_path / "invoice_sncf_2026-02-02.txt").write_text("invoice from SNCF total: €112")
    (tmp_path / "receipt_sncf_2026-02-02.txt").write_text("receipt from SNCF total: €12")
    idx = build_index(tmp_path)
    ans = answer_query("which invoice mentions SNCF?", idx, None)
    assert "invoice_sncf" in ans.citations[0].file
    assert all("emb" not in d for d in idx)


def test_index_skips_images_without_vision(tmp_path):
    (tmp_path / "shot.png").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("hello world")
    idx = build_index(tmp_path)
    assert idx and all("shot.png" not in d["file"] for d in idx)


def test_chunking_description_and_intent():
    assert chunk_text("") == []
    assert chunk_text("hello world")
    desc = describe_file("receipt_edf_2026-03-14.txt",
                         "date: 2026-03-14\ntotal: €87.40")
    assert "receipt" in desc and "edf" in desc and "87.40" in desc
    intent = parse_intent("how much did EDF charge in March 2026?")
    assert intent.wants_amount and intent.months == {3} and "2026" in intent.years
    assert "edf" in intent.expanded
