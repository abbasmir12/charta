"""The metadata index: what Charta knows about every file, and searching it."""
from __future__ import annotations

import pathlib

from charta.core import index_db, meta
from charta.core.ask import build_index, index_from_db
from charta.core.charter import preset_charter
from charta.core.pipeline import process_new_file


def _folder(tmp_path) -> pathlib.Path:
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "sponsorship_2026.txt").write_text(
        "Sponsorship agreement 2026 with Acme Corp. Amount: 5000 EUR Date: 2026-02-10",
        encoding="utf-8")
    (folder / "receipt_edf_2026-03-14.txt").write_text(
        "receipt from EDF date: 2026-03-14 total: 87.40 category: electricity",
        encoding="utf-8")
    return folder


def test_metadata_describes_a_file_without_guessing(tmp_path):
    folder = _folder(tmp_path)
    text = (folder / "receipt_edf_2026-03-14.txt").read_text(encoding="utf-8")
    info = meta.extract_metadata("receipt_edf_2026-03-14.txt", text)
    assert info["doc_type"] == "receipt"
    assert "edf" in info["tags"] and "2026" in info["tags"]
    assert info["fields"]["date"] == "2026-03-14"
    assert info["fields"]["amount"] == "87.40"
    assert "electricity" in info["description"] or "edf" in info["description"]


def test_the_index_is_filled_while_the_folder_is_scanned(tmp_path):
    folder = _folder(tmp_path)
    charter = preset_charter("freelancer")
    for path in sorted(folder.iterdir()):
        process_new_file(folder, path, charter)
    stats = index_db.stats(folder)
    assert stats["files"] == 2
    assert stats["chunks"] >= 2
    names = {f["path"] for f in index_db.files(folder)}
    assert names == {"sponsorship_2026.txt", "receipt_edf_2026-03-14.txt"}


def test_search_finds_files_by_name_tag_field_and_text(tmp_path):
    folder = _folder(tmp_path)
    charter = preset_charter("freelancer")
    for path in sorted(folder.iterdir()):
        process_new_file(folder, path, charter)
    by_name = index_db.search(folder, "sponsorship")
    assert by_name and by_name[0]["path"] == "sponsorship_2026.txt"
    by_tag = index_db.search(folder, "electricity")
    assert by_tag and by_tag[0]["path"] == "receipt_edf_2026-03-14.txt"
    by_amount = index_db.search(folder, "5000")
    assert by_amount and by_amount[0]["path"] == "sponsorship_2026.txt"
    assert index_db.search(folder, "nothinglikethis") == []


def test_ask_works_from_the_index_without_reading_the_files_again(tmp_path):
    folder = _folder(tmp_path)
    charter = preset_charter("freelancer")
    for path in sorted(folder.iterdir()):
        process_new_file(folder, path, charter)
    # The files are gone, but the index still answers.
    for path in folder.iterdir():
        if path.is_file():
            path.unlink()
    docs = index_from_db(folder)
    assert docs
    assert {d["file"] for d in docs} == {"sponsorship_2026.txt",
                                         "receipt_edf_2026-03-14.txt"}


def test_a_moved_file_keeps_its_metadata(tmp_path):
    folder = _folder(tmp_path)
    charter = preset_charter("freelancer")
    process_new_file(folder, folder / "sponsorship_2026.txt", charter)
    assert index_db.stats(folder)["files"] == 1
    (folder / "Sponsorships").mkdir()
    (folder / "sponsorship_2026.txt").rename(folder / "Sponsorships" / "sponsorship_2026.txt")
    # The index still knows the file under its old name; the move is recorded
    # by the journal and the file is re-indexed when it is seen again.
    assert index_db.stats(folder)["files"] == 1
