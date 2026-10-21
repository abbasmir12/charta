"""Background watcher: keeps every watched folder live.

The local backend hosts this thread, so watching continues while the window is
closed to the tray. It re-reads the watchlist every few seconds, so adding a
folder from the UI needs no restart. Each newly seen folder gets one initial scan
(existing files become proposals) and then a live observer for new files.
"""
from __future__ import annotations

import pathlib
import threading
from typing import Callable

from . import record
from . import watchlist
from .charter import load_charter
from .config import AppConfig
from .llm import LLMClient
from .paths import assert_not_protected
from .pipeline import process_new_file
from .watcher import FolderWatcher, wait_stable

EXCLUDED_PARTS = {".charta"}
POLL_SECONDS = 3.0
SCAN_STABLE_SECONDS = 0.2


def scan_folder(folder: str | pathlib.Path, client: LLMClient | None = None,
                vision: object | None = None,
                progress: Callable[[int, int, str], None] | None = None) -> int:
    """One-shot pass over a folder's existing files; returns files proposed.

    Runs through the same safety path as the live watcher (protected paths,
    suggest vs auto mode, sensitive detection), so a scan never surprises you.
    ``progress`` is called with (done, total, current file) as the scan runs.
    """
    root = pathlib.Path(folder)
    charter = load_charter(root)
    if charter is None:
        return 0
    files = [p for p in sorted(root.rglob("*"))
             if p.is_file() and not any(part in EXCLUDED_PARTS for part in p.parts)]
    total = len(files)
    count = 0
    proposals = 0
    for i, p in enumerate(files, start=1):
        if progress:
            progress(i - 1, total, str(p.relative_to(root)))
        if not wait_stable(p, SCAN_STABLE_SECONDS):
            continue
        result = process_new_file(root, p, charter, client,
                                  auto_apply=(charter.mode == "auto"), vision=vision)  # type: ignore[arg-type]
        count += 1
        if result.proposal.status == "pending":
            proposals += 1
        if progress:
            progress(i, total, str(p.relative_to(root)))
    record.record_index(None, root, count, proposals)
    return count


class WatchDaemon:
    """Owns one FolderWatcher per watched folder, synced to the watchlist."""

    def __init__(self, cfg: AppConfig, poll_seconds: float = POLL_SECONDS) -> None:
        self.cfg = cfg
        self.poll_seconds = poll_seconds
        self._watchers: dict[str, FolderWatcher] = {}
        self._scanned: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._watchers)

    def tick(self) -> list[str]:
        """Reconcile running observers with the watchlist; scan new folders once."""
        wanted = set(watchlist.folders(self.cfg))
        with self._lock:
            current = set(self._watchers)
        for folder in wanted - current:
            self._start_one(folder)
        for folder in current - wanted:
            self._stop_one(folder)
        return self.active()

    def _start_one(self, folder: str) -> None:
        path = pathlib.Path(folder)
        try:
            assert_not_protected(path)
        except Exception:  # noqa: BLE001 - protected folders are simply skipped
            return
        client = LLMClient(self.cfg)
        vision = client.describe_image if self.cfg.vision else None
        if folder not in self._scanned:
            self._scanned.add(folder)
            try:
                scan_folder(path, client, vision)
            except Exception:  # noqa: BLE001 - a bad file must not kill the daemon
                pass

        def on_file(p: pathlib.Path) -> None:
            charter = load_charter(path)
            if charter is None:
                return
            try:
                process_new_file(path, p, charter, client,
                                 auto_apply=(charter.mode == "auto"), vision=vision)
            except Exception:  # noqa: BLE001
                pass

        w = FolderWatcher(path, on_file, self.cfg.stable_seconds)
        try:
            w.start()
        except Exception:  # noqa: BLE001 - watchdog missing or folder gone
            return
        with self._lock:
            self._watchers[folder] = w

    def _stop_one(self, folder: str) -> None:
        with self._lock:
            w = self._watchers.pop(folder, None)
        if w:
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass

    def start(self) -> "WatchDaemon":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="charta-watchd", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - never let the loop die
                pass
            self._stop.wait(self.poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        for folder in self.active():
            self._stop_one(folder)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
