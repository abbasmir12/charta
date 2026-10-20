"""Shared fixtures: a tiny fake OpenAI-compatible server.

Exercises the real HTTP path of charta.core.llm (routes, auth header, payload
shape, error handling) without needing Ollama or any provider installed.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

import pytest


@dataclass
class FakeProvider:
    base_url: str = ""
    requests: list[tuple[str, str, str | None, dict | None]] = field(default_factory=list)
    reply: Callable[[dict], str] = lambda payload: "fine"
    reject_json_format: bool = False
    fail_status: int = 0

    @property
    def posts(self) -> list[dict]:
        return [r[3] or {} for r in self.requests if r[0] == "POST"]

    @property
    def paths(self) -> list[str]:
        return [r[1] for r in self.requests]


def _make_handler(state: FakeProvider):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeOpenAI/1.0"

        def log_message(self, *args: Any) -> None:  # keep pytest output clean
            return

        def _json(self, status: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            state.requests.append(("GET", self.path, self.headers.get("Authorization"), None))
            if state.fail_status:
                self._json(state.fail_status, {"error": "boom"})
            elif self.path.rstrip("/").endswith("/models"):
                self._json(200, {"data": [{"id": "fake-model"}]})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
            state.requests.append(("POST", self.path, self.headers.get("Authorization"), payload))
            if state.fail_status:
                self._json(state.fail_status, {"error": "boom"})
                return
            if self.path.endswith("/chat/completions"):
                if state.reject_json_format and "response_format" in payload:
                    self._json(400, {"error": "response_format is not supported"})
                    return
                self._json(200, {"choices": [{"message": {"role": "assistant",
                                                          "content": state.reply(payload)}}]})
            elif self.path.endswith("/embeddings"):
                text = str(payload.get("input", ""))
                self._json(200, {"data": [{"embedding": [float(len(text)), 1.0]}]})
            else:
                self._json(404, {"error": "not found"})

    return Handler


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path_factory, monkeypatch):
    """Keep the watched-folder registry and logs out of the developer's real one."""
    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path_factory.mktemp("charta-state")))


@pytest.fixture(autouse=True)
def _cleanup_watch_daemon():
    """A watch daemon started by a test must not leak into the next one."""
    yield
    try:
        from charta.web import app as web_app

        web_app._stop_daemon()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def fake_provider():
    state = FakeProvider()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    state.base_url = f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
