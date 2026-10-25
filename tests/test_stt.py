"""Speech-to-text provider dispatch: local Whisper, Moonshine, system,
ElevenLabs (cloud). Faked backends keep these tests instant and offline."""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

import pytest

from charta.voice import stt


def test_normalize_maps_aliases_and_rejects_unknown():
    assert stt.normalize("") == "local"
    assert stt.normalize("whisper") == "local"
    assert stt.normalize("Eleven-Labs") == "elevenlabs"
    assert stt.normalize("SAPI") == "system"
    with pytest.raises(ValueError, match="Choose one of"):
        stt.normalize("podcast")


def test_transcribe_never_touches_a_missing_file(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("backend should not be called")

    monkeypatch.setitem(stt._HANDLERS, stt.LOCAL, boom)
    with pytest.raises(RuntimeError, match="never reached the server"):
        stt.transcribe("/tmp/definitely-not-there.wav", provider="local")


def test_transcribe_dispatches_and_strips(monkeypatch, tmp_path):
    seen = {}
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF0000WAVE0000")

    def fake_local(path, *, model="", api_key="", timeout=45.0):
        seen["model"] = model
        return "  spoken words  "

    monkeypatch.setitem(stt._HANDLERS, stt.LOCAL, fake_local)
    assert stt.transcribe(audio, provider="local", model="tiny") == "spoken words"
    assert seen["model"] == "tiny"


def test_as_wav_passes_through_a_real_wav(tmp_path):
    import wave
    wav = tmp_path / "real.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 100)
    assert stt.as_wav(wav) == wav


def test_elevenlabs_requires_a_key():
    with pytest.raises(RuntimeError, match="API key"):
        stt._elevenlabs("/tmp/never-read.wav", api_key="")


def test_elevenlabs_posts_multipart_with_xi_api_key(monkeypatch, tmp_path):
    import io
    sent = {}

    class Resp(io.BytesIO):
        # Real http responses support the context-manager protocol.
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req: urllib.request.Request, timeout):
        sent["url"] = req.full_url
        sent["headers"] = dict(req.headers)
        sent["body"] = req.data
        return Resp(json.dumps({"text": "invoice for March"}).encode())

    monkeypatch.setattr(stt, "as_wav", lambda p: pathlib.Path(p))
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    clip = tmp_path / "clip.webm"
    clip.write_bytes(b"\x1aE\xdf\xa3clipbytes")
    out = stt._elevenlabs(clip, api_key="el-key")
    assert out == "invoice for March"
    assert sent["url"] == stt.DEFAULT_ELEVENLABS_URL
    got_key = {k.lower(): v for k, v in sent["headers"].items()}.get("xi-api-key")
    assert got_key == "el-key"
    body = sent["body"].decode(errors="replace")
    assert "model_id" in body and "scribe_v1" in body
    assert 'name="file"; filename="clip.webm"' in body


def test_elevenlabs_bad_key_reads_as_a_friendly_error(monkeypatch, tmp_path):
    import io

    def fail(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(stt, "as_wav", lambda p: pathlib.Path(p))
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"RIFF" + b"0" * 64)
    with pytest.raises(RuntimeError, match="rejected the API key"):
        stt._elevenlabs(clip, api_key="wrong")


def test_moonshine_missing_package_message(monkeypatch, tmp_path):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "moonshine":
            raise ImportError("no moonshine")
        return real_import(name, *a, **k)

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF0000WAVE0000")
    builtins.__import__ = fake_import
    try:
        with pytest.raises(RuntimeError, match="useful-moonshine-onnx"):
            stt._moonshine(audio)
    finally:
        builtins.__import__ = real_import


def test_moonshine_accepts_str_list_and_dict_results(monkeypatch, tmp_path):
    import types
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF" + b"0" * 64)
    monkeypatch.setattr(stt, "as_wav", lambda p: pathlib.Path(p))
    count = 0
    for result in (["hello ", "there"], {"text": "hello there"}, "hello there"):
        fake = types.ModuleType("moonshine")
        fake.onnx_transcribe = lambda *a, _r=result, **k: _r
        monkeypatch.setitem(__import__("sys").modules, "moonshine", fake)
        out = stt._moonshine(audio, model="m")
        assert out == "hello there", result
        count += 1
    assert count == 3


def test_system_provider_without_package(monkeypatch):
    import builtins, pathlib
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "speech_recognition":
            raise ImportError("gone")
        return real_import(name, *a, **k)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(RuntimeError, match="system speech engine"):
            stt._system(pathlib.Path("/tmp/x.wav"))
    finally:
        builtins.__import__ = real_import


def test_cloud_labels_and_provider_labels():
    assert stt.cloud_label("elevenlabs") is True
    assert stt.cloud_label("moonshine") is False
    assert stt.provider_label("elevenlabs") == "ElevenLabs (cloud)"
    assert stt.provider_label("local") == "Local Whisper"


@pytest.mark.parametrize("p,mod", [("local", "faster_whisper"),
                                   ("moonshine", "moonshine"),
                                   ("system", "speech_recognition")])
def test_backend_available_follows_importability(monkeypatch, p, mod):
    monkeypatch.setattr(stt, "_importable", lambda name: name == mod)
    assert stt.backend_available(p) is True
    monkeypatch.setattr(stt, "_importable", lambda name: name != mod)
    assert stt.backend_available(p) is False


def test_leftover_fakes_are_not_imported_on_module_load():
    # The first voice wave shipped a stub that imported deps at module level;
    # a clean import must never touch the heavy stacks.
    import sys
    assert "moonshine" not in sys.modules
    assert "faster_whisper" not in sys.modules
