"""The background watcher: initial scan, live tracking, and protected-folder skip."""
from __future__ import annotations

from charta.core import proposals as prop_store
from charta.core import watchlist
from charta.core.charter import preset_charter, save_charter
from charta.core.config import AppConfig
from charta.core.watchd import WatchDaemon, scan_folder


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(state_dir=str(tmp_path / "state"), stable_seconds=0.1)


def test_scan_folder_proposes_existing_files(tmp_path):
    folder = tmp_path / "stuff"
    folder.mkdir()
    save_charter(folder, preset_charter("student"))
    (folder / "lecture_07.txt").write_text("lecture 7 notes", encoding="utf-8")
    assert scan_folder(folder) == 1
    props = prop_store.load_proposals(folder)
    assert props and props[0].source == "lecture_07.txt" and props[0].reason


def test_scan_folder_ignores_its_own_charta_dir(tmp_path):
    folder = tmp_path / "stuff"
    folder.mkdir()
    save_charter(folder, preset_charter("student"))
    assert scan_folder(folder) == 0  # .charta/ must never be proposed


def test_scan_without_a_charter_does_nothing(tmp_path):
    folder = tmp_path / "nocharter"
    folder.mkdir()
    (folder / "a.txt").write_text("x", encoding="utf-8")
    assert scan_folder(folder) == 0


def test_daemon_scans_new_folders_and_drops_removed_ones(tmp_path):
    cfg = _cfg(tmp_path)
    folder = tmp_path / "watched"
    folder.mkdir()
    save_charter(folder, preset_charter("student"))
    (folder / "lecture_01.txt").write_text("lecture 1", encoding="utf-8")
    watchlist.add(cfg, folder)

    daemon = WatchDaemon(cfg, poll_seconds=0.1)
    try:
        assert daemon.tick() == [str(folder.resolve())]
        assert prop_store.load_proposals(folder)  # the initial scan ran
        watchlist.remove(cfg, folder)
        assert daemon.tick() == []
        assert daemon.active() == []
    finally:
        daemon.stop()


def test_daemon_skips_protected_folders(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    folder = tmp_path / "system"
    folder.mkdir()
    watchlist.add(cfg, folder)

    def refuse(_path):
        raise RuntimeError("protected")

    monkeypatch.setattr("charta.core.watchd.assert_not_protected", refuse)
    daemon = WatchDaemon(cfg, poll_seconds=0.1)
    try:
        assert daemon.tick() == []
    finally:
        daemon.stop()
