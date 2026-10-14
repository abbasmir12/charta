"""Web UI polish: debug flag, icon, protected refusal, folder picker, charter mode."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from charta.core.charter import load_charter
from charta.web.app import app


@pytest.fixture
def client(monkeypatch):
    # Point the provider at a closed port: AI calls fail fast and fall back.
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:9/v1")
    return TestClient(app)


def test_debug_flag_defaults_off_and_follows_env(client, monkeypatch):
    monkeypatch.delenv("CHARTA_DEBUG", raising=False)
    assert "window.__CHARTA_DEBUG__=false" in client.get("/").text
    monkeypatch.setenv("CHARTA_DEBUG", "1")
    assert "window.__CHARTA_DEBUG__=true" in client.get("/").text


def test_favicon_is_the_multi_size_ico(client):
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert res.content[:6] == b"\x00\x00\x01\x00\x07\x00"


def test_protected_refusal_page_is_friendly(client):
    res = client.get("/protected?folder=C:\\Windows")
    assert res.status_code == 200
    assert "won't watch this folder" in res.text
    assert "Nothing here was read, moved or changed" in res.text


def test_folder_picker_api_lists_only_folders(client, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "a.txt").write_text("x")
    body = client.get("/api/fs/list", params={"path": str(tmp_path)}).json()
    assert body["dirs"] == ["docs"] and body["protected"] is False
    assert body["path"] and body["roots"]


def test_charter_is_refused_for_protected_folders(client):
    res = client.post("/api/charter", params={"folder": "C:\\Windows"}, json={"purpose": "sneaky"})
    assert res.status_code == 403
    assert res.json()["error"] == "protected"
    assert "protected" in res.json()["message"].lower()


def test_charter_persists_the_chosen_mode(client, tmp_path):
    res = client.post("/api/charter", params={"folder": str(tmp_path)},
                      json={"purpose": "receipts and invoices", "mode": "auto"})
    assert res.status_code == 200 and res.json()["mode"] == "auto"
    charter = load_charter(tmp_path)
    assert charter is not None and charter.mode == "auto"


def test_setup_screen_has_picker_and_custom_dropdown(client):
    html = client.get("/").text
    assert 'id="fsPicker"' in html and "openPicker()" in html
    assert 'class="dd"' in html and "<select" not in html
