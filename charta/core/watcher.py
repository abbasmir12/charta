"""Stable-file watcher (waits until size settles) + watchdog wrapper."""
from __future__ import annotations

import pathlib
import time
from typing import Callable


def wait_stable(path: str | pathlib.Path, stable_seconds: float = 2.0,
                poll: float = 0.5, timeout: float = 60.0) -> bool:
    p = pathlib.Path(path)
    start = time.time()
    last_size = -1
    stable_since = time.time()
    while time.time() - start < timeout:
        try:
            size = p.stat().st_size
        except FileNotFoundError:
            return False
        now = time.time()
        if size == last_size:
            if now - stable_since >= stable_seconds:
                return True
        else:
            stable_since = now
            last_size = size
        time.sleep(poll)
    return False


class FolderWatcher:
    def __init__(self, folder: str | pathlib.Path, on_stable_file: Callable[[pathlib.Path], None],
                 stable_seconds: float = 2.0) -> None:
        self.folder = pathlib.Path(folder)
        self.on_stable_file = on_stable_file
        self.stable_seconds = stable_seconds
        self._observer = None

    def start(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError as e:
            raise RuntimeError("watchdog not installed. pip install watchdog") from e

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):  # noqa: N802
                if not event.is_directory:
                    p = pathlib.Path(str(event.src_path))
                    if ".charta" in p.parts:
                        return
                    if wait_stable(p, watcher.stable_seconds):
                        watcher.on_stable_file(p)

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.folder), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
