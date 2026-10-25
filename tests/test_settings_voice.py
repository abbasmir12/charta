"""Voice settings: full Settings UI save (config.toml write) + /api/voice.

The settings API is the UI's way to edit everything a user could otherwise
hand-edit in config.toml — provider, base URL, keys, models. Secrets never
leave the server: GET reports api_key_set, never the key itself.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from charta.core import config as config_mod
from charta.web.app import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Each test gets its own config.toml (CHARTA_CONFIG) + closed provider."""
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("CHARTA_CONFIG", str(tmp_path / "config.toml"))
    return TestClient(app)


# ── GET /api/settings ────────────────────────────────────────────────────


def test_settings_get_reports_file_values_and_never_secrets(client):
    get = client.get("/api/settings").json()
    assert get["config_path"].endswith("config.toml")
    assert set(get["llm"]) >= {"provider", "base_url", "api_key_set",
                               "generation", "timeout_seconds", "retries"}
    assert set(get["voice"]) >= {"provider", "whisper_model", "stt_model",
                                 "api_key_set", "cloud", "backends"}
    # A secret is a boolean here, never a string.
    assert isinstance(get["llm"]["api_key_set"], bool)
    assert isinstance(get["voice"]["api_key_set"], bool)


def test_settings_get_lists_all_providers_with_availability(client):
    get = client.get("/api/settings").json()
    assert "ollama" in get["providers"] and "custom" in get["providers"]
    assert set(get["voice"]["backends"]) == {"local", "moonshine", "system",
                                             "elevenlabs"}


# ── POST /api/settings ───────────────────────────────────────────────────


def test_settings_post_writes_voice_and_llm_to_config(client, tmp_path):
    body = {"llm": {"provider": "openrouter", "base_url": "", "api_key": "",
                    "generation": "qwen3:8b", "vision_model": "",
                    "vision": False, "timeout_seconds": 90, "retries": 2},
            "voice": {"provider": "moonshine", "whisper_model": "small",
                      "stt_model": "moonshine-base-ONNX", "api_key": ""}}
    res = client.post("/api/settings", json=body)
    assert res.status_code == 200, res.text
    path = pathlib.Path(res.json()["path"])
    doc = config_mod.load_document(path)
    assert doc["llm"]["provider"] == "openrouter"
    assert doc["models"]["generation"] == "qwen3:8b"
    assert doc["models"]["timeout_seconds"] == 90
    assert doc["models"]["retries"] == 2
    assert doc["llm"]["vision"] is False
    assert doc["voice"]["provider"] == "moonshine"
    assert doc["voice"]["stt_model"] == "moonshine-base-ONNX"
    # The GET, re-read, shows the same thing (server reloads config per request).
    get = client.get("/api/settings").json()
    assert get["llm"]["provider"] == "openrouter"
    assert get["voice"]["provider"] == "moonshine"
    assert get["voice"]["cloud"] is False


def test_settings_post_stores_and_clears_a_secret(client, tmp_path):
    client.post("/api/settings",
                json={"llm": {"api_key": "sk-test-123"}})
    doc = config_mod.load_document(config_mod.config_path())
    assert doc["llm"]["api_key"] == "sk-test-123"
    assert client.get("/api/settings").json()["llm"]["api_key_set"] is True
    # An empty string keeps the stored key.
    client.post("/api/settings", json={"llm": {"api_key": "", "provider": ""}})
    assert config_mod.load_document(config_mod.config_path())["llm"]["api_key"] \
        == "sk-test-123"
    # null explicitly clears it.
    client.post("/api/settings", json={"llm": {"api_key": None}})
    assert config_mod.load_document(config_mod.config_path())["llm"]["api_key"] == ""
    assert client.get("/api/settings").json()["llm"]["api_key_set"] is False


def test_settings_post_keeps_keys_it_was_not_told_about(client):
    client.post("/api/settings", json={"llm": {"api_key": "keep-me"}})
    # A partial update that only touches voice must not lose the LLM key.
    client.post("/api/settings", json={"voice": {"provider": "local"}})
    doc = config_mod.load_document(config_mod.config_path())
    assert doc["llm"]["api_key"] == "keep-me"


def test_settings_post_rejects_unknown_provider_and_bad_url(client):
    r1 = client.post("/api/settings", json={"llm": {"provider": "not-a-thing"}})
    assert r1.status_code == 400
    r2 = client.post("/api/settings",
                     json={"llm": {"base_url": "javascript:alert(1)"}})
    assert r2.status_code == 400
    r3 = client.post("/api/settings", json={"voice": {"provider": "wat"}})
    assert r3.status_code == 400


def test_settings_post_drops_stale_stock_base_url(client):
    # Switching from ollama (stock URL stored) to openrouter without a new
    # URL must not leave the dead localhost endpoint in the file.
    client.post("/api/settings",
                json={"llm": {"provider": "ollama",
                              "base_url": "http://localhost:11434/v1"}})
    client.post("/api/settings", json={"llm": {"provider": "openrouter"}})
    doc = config_mod.load_document(config_mod.config_path())
    assert doc["llm"]["base_url"] == ""


# ── POST /api/voice ──────────────────────────────────────────────────────


def test_voice_uses_the_configured_provider_and_returns_transcript(
        client, monkeypatch, tmp_path):
    cfg = {"hits": []}
    import charta.voice.stt as stt
    from charta.web import app as web

    monkeypatch.setattr(stt, "transcribe",
                        lambda audio, *, provider, model, api_key, timeout=45.0:
                        cfg["hits"].append((provider, model, api_key))
                        or "what is this folder for")
    monkeypatch.setattr(web, "_cfg",
                        lambda: config_mod.AppConfig(
                            voice_provider="moonshine",
                            stt_model="moonshine-base-ONNX"))
    res = client.post("/api/voice?ext=webm", content=b"RIFFfake",
                      headers={"Content-Type": "audio/webm"})
    assert res.status_code == 200, res.text
    assert res.json()["text"] == "what is this folder for"
    assert res.json()["provider"] == "moonshine"
    assert cfg["hits"] == [("moonshine", "moonshine-base-ONNX",
                            config_mod.AppConfig().voice_api_key)]


def test_voice_forwarding_error_is_friendly_json(client, monkeypatch):
    import charta.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("Moonshine speech-to-text is not installed.")))
    res = client.post("/api/voice", content=b"x")
    assert res.status_code == 400
    assert res.json()["error"] == "Moonshine speech-to-text is not installed."


def test_voice_rejects_empty_body_and_unknown_provider(client, monkeypatch):
    empty = client.post("/api/voice", content=b"")
    assert empty.status_code == 400
    res = client.post("/api/voice?provider=podcast", content=b"x")
    assert res.status_code == 400
    assert "Unknown speech-to-text provider" in res.json()["error"]


def test_settings_page_renders_the_editable_form(client):
    html = client.get("/settings").text
    assert 'id="settingsform"' in html
    assert 'name="st-llm-provider"' in html
    assert 'name="st-llm-base_url"' in html
    assert 'name="st-llm-api_key"' in html and 'type="password"' in html
    assert 'name="st-voice-provider"' in html
    assert "Save settings" in html
