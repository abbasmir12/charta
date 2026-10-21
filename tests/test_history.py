"""Folder history: a private git repo that records what Charta changed.

These tests need git on PATH; when it is missing they are skipped rather than
failing, because Charta is designed to work without it.
"""
from __future__ import annotations

import pathlib

import pytest

from charta.core import history, record
from charta.core.config import AppConfig

pytestmark = pytest.mark.skipif(not history.available(), reason="git is not installed")


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(state_dir=str(tmp_path / "state"))


def test_a_folder_gets_a_private_repository_not_a_visible_dot_git(tmp_path):
    folder = tmp_path / "receipts"
    folder.mkdir()
    assert history.ensure(folder) is True
    assert (folder / ".charta" / "git" / "HEAD").exists()
    assert not (folder / ".git").exists()


def test_commits_are_recorded_with_a_readable_message(tmp_path):
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "note.txt").write_text("hello", encoding="utf-8")
    sha = history.commit(folder, "charta: indexed 1 file — 1 proposal")
    assert sha and len(sha) == 40
    log = history.log(folder)
    assert log and log[0]["message"].startswith("charta: indexed 1 file")
    assert log[0]["files"] == "note.txt"


def test_the_history_never_records_chartas_own_bookkeeping(tmp_path):
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "note.txt").write_text("hello", encoding="utf-8")
    history.commit(folder, "charta: first")
    (folder / ".charta" / "charter.md").write_text("# charter", encoding="utf-8")
    history.commit(folder, "charta: second")
    files = " ".join(c["files"] for c in history.log(folder))
    assert ".charta" not in files


def test_an_older_version_of_a_file_can_be_restored(tmp_path):
    folder = tmp_path / "receipts"
    folder.mkdir()
    target = folder / "note.txt"
    target.write_text("first", encoding="utf-8")
    sha = history.commit(folder, "charta: first version")
    target.write_text("second", encoding="utf-8")
    history.commit(folder, "charta: second version")

    assert history.read_at(folder, sha, "note.txt") == "first"
    assert history.restore_file(folder, sha, "note.txt")
    assert target.read_text(encoding="utf-8") == "first"
    # The current file is kept, never thrown away.
    assert (folder / "note.txt.charta-old").read_text(encoding="utf-8") == "second"


def test_moves_are_recorded_with_the_reason(tmp_path):
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "a.txt").write_text("a", encoding="utf-8")
    record.record_moves(_cfg(tmp_path), folder,
                        [("a.txt", "Invoices/a.txt", "it is an invoice dated March 2026")])
    log = history.log(folder)
    assert log[0]["message"] == "charta: moved a.txt → Invoices/a.txt — it is an invoice dated March 2026"


def test_history_can_be_switched_off(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.history = False
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "a.txt").write_text("a", encoding="utf-8")
    assert record.record(cfg, folder, "charta: nope") is None
    assert not history.is_ready(folder)
