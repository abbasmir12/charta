"""File tools: read, edit and put aside — never destroying anything."""
from __future__ import annotations

import pytest

from charta.core import tools


def test_editing_keeps_the_previous_version(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("first", encoding="utf-8")
    result = tools.write(tmp_path, "notes.md", "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert result["backup"] == "notes.md.charta-old"
    assert (tmp_path / "notes.md.charta-old").read_text(encoding="utf-8") == "first"


def test_writing_a_new_file_creates_it(tmp_path):
    result = tools.write(tmp_path, "sub/new.md", "hello")
    assert (tmp_path / "sub" / "new.md").read_text(encoding="utf-8") == "hello"
    assert result["backup"] == ""


def test_trash_moves_the_file_and_keeps_it(tmp_path):
    target = tmp_path / "old.txt"
    target.write_text("keep me", encoding="utf-8")
    result = tools.trash(tmp_path, "old.txt")
    assert not target.exists()
    kept = tmp_path / result["to"]
    assert kept.read_text(encoding="utf-8") == "keep me"
    assert tools.trash_listing(tmp_path)[0]["was"] == "old.txt"


def test_a_trashed_file_can_be_brought_back(tmp_path):
    target = tmp_path / "old.txt"
    target.write_text("keep me", encoding="utf-8")
    result = tools.trash(tmp_path, "old.txt")
    restored = tools.restore(tmp_path, result["to"])
    assert restored["restored"] == "old.txt"
    assert target.read_text(encoding="utf-8") == "keep me"
    assert tools.trash_listing(tmp_path) == []


def test_tools_refuse_to_touch_anything_outside_the_folder(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(tools.ToolError):
        tools.write(tmp_path, "../secret.txt", "hacked")
    with pytest.raises(tools.ToolError):
        tools.trash(tmp_path, "../secret.txt")
    assert outside.read_text(encoding="utf-8") == "nope"


def test_tools_refuse_to_write_over_chartas_own_files(tmp_path):
    with pytest.raises(tools.ToolError):
        tools.write(tmp_path, ".charta/charter.md", "hacked")


def test_trashing_a_missing_file_says_so(tmp_path):
    with pytest.raises(tools.ToolError):
        tools.trash(tmp_path, "nope.txt")
