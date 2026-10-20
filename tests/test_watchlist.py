"""Watched-folders registry: idempotent add, remove, and tolerance for junk."""
from __future__ import annotations

from charta.core import watchlist
from charta.core.config import AppConfig


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(state_dir=str(tmp_path / "state"))


def test_add_is_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    watchlist.add(cfg, tmp_path / "receipts")
    watchlist.add(cfg, tmp_path / "receipts")
    assert len(watchlist.folders(cfg)) == 1


def test_paths_are_normalised_so_any_form_matches(tmp_path):
    cfg = _cfg(tmp_path)
    folder = tmp_path / "docs"
    folder.mkdir()
    watchlist.add(cfg, folder, mode="auto")
    assert watchlist.is_watched(cfg, folder)
    assert watchlist.is_watched(cfg, str(folder))
    assert watchlist.load(cfg)[0]["mode"] == "auto"


def test_remove_returns_the_remaining_folders(tmp_path):
    cfg = _cfg(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    watchlist.add(cfg, a)
    watchlist.add(cfg, b)
    remaining = watchlist.remove(cfg, a)
    assert len(remaining) == 1
    assert not watchlist.is_watched(cfg, a)
    assert watchlist.is_watched(cfg, b)


def test_corrupt_registry_is_tolerated(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.state_path().mkdir(parents=True, exist_ok=True)
    (cfg.state_path() / "watched.json").write_text("{ not json", encoding="utf-8")
    assert watchlist.load(cfg) == []
    assert watchlist.folders(cfg) == []
