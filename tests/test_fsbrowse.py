"""Folder picker listing: folders only, protected paths flagged, never raises."""
from __future__ import annotations

import os
import pathlib

from charta.core import fsbrowse


def test_lists_only_subfolders(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "Beta").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "note.txt").write_text("x")
    listing = fsbrowse.list_dirs(str(tmp_path))
    assert listing.dirs == ["alpha", "Beta"]  # case-insensitive sort, no files/dotdirs
    assert pathlib.Path(listing.parent) == pathlib.Path(listing.path).parent
    assert listing.protected is False and listing.exists


def test_parent_of_root_drive_is_none(tmp_path):
    listing = fsbrowse.list_dirs(str(tmp_path))
    assert listing.parent is not None
    assert fsbrowse.list_dirs(os.sep).parent is None


def test_protected_folder_is_listed_but_flagged(tmp_path):
    listing = fsbrowse.list_dirs(str(tmp_path))
    assert listing.protected is False
    if os.path.isdir("/etc"):  # posix system dir from the AGENTS blocklist
        protected = fsbrowse.list_dirs("/etc")
        assert protected.protected is True and protected.exists


def test_missing_and_not_a_folder(tmp_path):
    missing = fsbrowse.list_dirs(str(tmp_path / "nope"))
    assert missing.exists is False and missing.error and missing.roots
    (tmp_path / "file.txt").write_text("x")
    listing = fsbrowse.list_dirs(str(tmp_path / "file.txt"))
    assert listing.exists is False and listing.error == "Not a folder"


def test_defaults_to_home_with_drives(tmp_path):
    listing = fsbrowse.list_dirs(None)
    assert listing.path == fsbrowse.home_dir()
    assert listing.roots
    assert isinstance(listing.as_dict(), dict)
