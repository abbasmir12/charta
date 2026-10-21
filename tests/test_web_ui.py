"""Web UI polish: debug flag, icon, protected refusal, folder picker, charter mode."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from charta.core.charter import load_charter
from charta.web.app import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Point the provider at a closed port: AI calls fail fast and fall back.
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:9/v1")
    # Keep the watched-folder registry inside the test's temp dir.
    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path / "state"))
    return TestClient(app)


def test_health_never_waits_on_the_provider(client, monkeypatch):
    """The launcher probes /api/health with a 1.5s timeout; a model ping there
    used to make a healthy server look dead."""
    from charta.core.llm import LLMClient

    def boom(*_a, **_k):
        raise AssertionError("/api/health must not call the model")

    monkeypatch.setattr(LLMClient, "ping", boom)
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["provider"] and "llm" not in body


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


def test_watch_requires_a_charter(client, tmp_path):
    res = client.post("/api/watch", params={"folder": str(tmp_path)})
    assert res.status_code == 400
    assert res.json()["error"] == "no-charter"


def test_watch_unwatch_and_status_round_trip(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    res = client.post("/api/watch", params={"folder": str(tmp_path)})
    assert res.status_code == 200 and res.json()["watching"] is True

    status = client.get("/api/watch/status", params={"folder": str(tmp_path)}).json()
    assert status["watching"] is True
    assert str(tmp_path.resolve()) in status["folders"]

    res = client.post("/api/unwatch", params={"folder": str(tmp_path)})
    assert res.json()["watching"] is False
    assert str(tmp_path.resolve()) not in client.get(
        "/api/watch/status").json()["folders"]


def test_scan_endpoint_proposes_existing_files(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    body = client.post("/api/scan", params={"folder": str(tmp_path)}).json()
    assert body["scanned"] == 1 and body["tracked"] == 1


def test_watch_is_refused_for_protected_folders(client):
    res = client.post("/api/watch", params={"folder": "C:\\Windows"})
    assert res.status_code == 403 and res.json()["error"] == "protected"


def test_setup_redirects_to_overview_when_a_charter_exists(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    res = client.get("/", params={"folder": str(tmp_path)}, follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"].startswith("/overview")


def test_setup_redirects_protected_folder_to_the_refusal_screen(client):
    res = client.get("/", params={"folder": "C:\\Windows"}, follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "/protected" in res.headers["location"]



def test_folders_page_lists_the_watched_folders(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    client.post("/api/watch", params={"folder": str(tmp_path)})
    text = client.get("/folders").text
    assert "Watched folders" in text
    assert tmp_path.name in text
    assert "1 folder watched" in text
    assert "Ask about this folder" in text or "Ask about" in text


def test_unwatching_keeps_the_folder_and_its_analysis(client, tmp_path):
    from charta.core.charter import preset_charter, save_charter

    save_charter(tmp_path, preset_charter("student"))
    (tmp_path / "lecture_07.txt").write_text("lecture 7", encoding="utf-8")
    client.post("/api/watch", params={"folder": str(tmp_path)})
    client.post("/api/scan", params={"folder": str(tmp_path)})
    client.post("/api/unwatch", params={"folder": str(tmp_path)})

    text = client.get("/folders").text
    assert "Paused" in text and "Resume watching" in text
    assert "0 folders watched" in text
    # The analysis is still there: the file keeps its index state.
    files = client.get("/files", params={"folder": str(tmp_path)}).text
    assert "lecture_07.txt" in files and "pending" in files


def test_files_page_lists_files_and_reads_them(client, tmp_path):
    (tmp_path / "notes.md").write_text("hello from the folder", encoding="utf-8")
    text = client.get("/files", params={"folder": str(tmp_path)}).text
    assert "notes.md" in text and "Read" in text
    body = client.get("/api/file/read", params={"folder": str(tmp_path),
                                                 "path": "notes.md"}).json()
    assert body["text"] == "hello from the folder"
    assert body["method"] == "text"


def test_file_read_refuses_paths_outside_the_folder(client, tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    res = client.get("/api/file/read", params={"folder": str(tmp_path),
                                                "path": "../secret.txt"})
    assert res.status_code == 400
    assert res.json()["error"] == "outside-folder"
