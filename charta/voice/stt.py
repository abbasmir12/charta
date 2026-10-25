"""Speech-to-text behind one interface.

Providers (``charta.voice.stt.transcribe(..., provider=...)``):

- ``local``      faster-whisper, fully offline (default).
- ``moonshine``  local Moonshine ONNX model (tiny and fast); needs the
                 optional ``moonshine`` package and the model downloaded.
- ``system``     the OS speech engine via the optional ``SpeechRecognition``
                 package — no AI model at all.
- ``elevenlabs`` CLOUD (opt-in): audio is uploaded to elevenlabs.io. Never
                 the default, and the config UI labels it as cloud.

Every path raises a friendly RuntimeError when its backend is missing, so the
caller can show a calm message instead of a stack trace.
"""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

LOCAL = "local"
MOONSHINE = "moonshine"
SYSTEM = "system"
ELEVENLABS = "elevenlabs"

PROVIDERS: tuple[str, ...] = (LOCAL, MOONSHINE, SYSTEM, ELEVENLABS)
CLOUD_PROVIDERS = {ELEVENLABS}

CLOUD_NOTICE = ("ElevenLabs speech-to-text is CLOUD: audio leaves your device. "
                "It is off by default and requires opt-in.")

DEFAULT_ELEVENLABS_URL = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_ELEVENLABS_MODEL = "scribe_v1"


def _uri(p: str | pathlib.Path) -> str:
    return str(p)


def normalize(provider: str) -> str:
    """Accept the friendly aliases and return a known provider name."""
    p = str(provider or "").strip().lower()
    if p in ("", "local", "whisper", "faster-whisper"):
        return LOCAL
    if p in ("moonshine",):
        return MOONSHINE
    if p in ("system", "os", "sapi"):
        return SYSTEM
    if p in ("elevenlabs", "eleven-labs"):
        return ELEVENLABS
    raise ValueError(
        f"Unknown speech-to-text provider {p!r}. Choose one of: "
        + ", ".join(PROVIDERS))


# ── Audio prep ───────────────────────────────────────────────────────────
# Browsers record webm/ogg; local model packages expect PCM WAV. PyMuPDF's
# sibling PyAV (bundled with faster-whisper) decodes anything, so local
# providers get a normalised 16 kHz mono WAV copy and never fail on format.


def as_wav(audio_path: str | pathlib.Path) -> pathlib.Path:
    """Return a path holding PCM WAV audio (16 kHz mono), converting if needed.

    Never raises on a healthy WAV; raises a friendly error when the audio is
    unreadable or no decoder is installed.
    """
    src = pathlib.Path(audio_path)
    if src.suffix.lower() in (".wav", ".wave") and src.stat().st_size > 44:
        return src
    try:
        import av  # PyAV ships with faster-whisper
    except ImportError as e:
        raise RuntimeError(
            "No audio decoder available. Run: pip install faster-whisper "
            "(it brings PyAV for webm/m4a/ogg support).") from e
    import tempfile
    import wave
    out = pathlib.Path(tempfile.mktemp(prefix="charta-voice-", suffix=".wav"))
    try:
        container = av.open(_uri(src))
        with container, wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.setcomptype("NONE", "NONE")  # uncompressed PCM
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                for r in resampler.resample(frame):
                    w.writeframes(bytes(r.planes[0]))
    except Exception as e:  # noqa: BLE001 - any decode trouble is user-facing
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not read the recorded audio ({type(e).__name__}). "
            "Try a different speech-to-text provider in Settings.") from e
    return out


# ── faster-whisper (default, local) ──────────────────────────────────────


def _whisper(audio: str | pathlib.Path, *, model: str = "small") -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "Local Whisper speech-to-text is not installed. Run: "
            "pip install faster-whisper") from e
    m = WhisperModel(model or "small", device="cpu", compute_type="int8")
    segments, _ = m.transcribe(_uri(as_wav(audio)))
    return " ".join(s.text for s in segments).strip()


# ── Moonshine (local, tiny ONNX) ─────────────────────────────────────────


def _moonshine(audio: str | pathlib.Path, *, model: str = "") -> str:
    try:
        import moonshine
    except ImportError as e:
        raise RuntimeError(
            "Moonshine speech-to-text is not installed on this machine. "
            "Run: pip install useful-moonshine-onnx, then download the model "
            "once (see Settings → Voice).") from e
    name = model or "moonshine-base-ONNX"
    txt: object = None
    call = getattr(moonshine, "onnx_transcribe", None)
    if call is not None:
        result = call(_uri(as_wav(audio)), model_name=name)
    else:  # older package shape: moonshine.transcribe(...)
        call = getattr(moonshine, "transcribe", None)
        if call is None:
            raise RuntimeError(
                "The installed moonshine package has no usable transcribe "
                "API. Install useful-moonshine-onnx instead.")
        result = call(_uri(as_wav(audio)), model_name=name)
    # The API has gone through str / dict / list shapes over versions.
    if isinstance(result, dict):
        txt = result.get("text", "")
    elif isinstance(result, (list, tuple)):
        txt = "".join(part if isinstance(part, str) else str(part)
                      for part in result)
    else:
        txt = result
    return str(txt or "").strip()


# ── System speech engine (no AI model) ───────────────────────────────────


def _system(audio: str | pathlib.Path, **_: object) -> str:
    try:
        import speech_recognition as sr
    except ImportError as e:
        raise RuntimeError(
            "No system speech engine found. Install the optional helper: "
            "pip install SpeechRecognition  (or switch to Moonshine / "
            "Whisper in Settings → Voice).") from e
    rec = sr.Recognizer()
    with sr.AudioFile(_uri(as_wav(audio))) as source:
        data = rec.record(source)
    for engine in ("recognize_sapi", "recognize_google", "recognize_sphinx"):
        fn = getattr(rec, engine, None)
        if fn is None:
            continue
        try:
            return str(fn(rec, data) or "").strip()
        except Exception:  # noqa: BLE001 - try the next engine
            continue
    raise RuntimeError(
        "The system speech engine could not transcribe this clip "
        "(no offline engine installed). Choose Moonshine or Whisper "
        "in Settings → Voice.")


# ── ElevenLabs (cloud, opt-in) ───────────────────────────────────────────


def post_multipart(url: str, *, api_key: str, filename: str,
                   content_type: str, data: bytes, extra_fields: dict[str, str],
                   timeout: float) -> bytes:
    """POST a single multipart file upload (std-lib only) and return the body."""
    boundary = "charta-voice-8f3a2c"
    parts: list[bytes] = []
    for field, value in extra_fields.items():
        parts.append(
            (f"--{boundary}\r\nContent-Disposition: form-data; "
             f"name=\"{field}\"\r\n\r\n{value}\r\n").encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
         f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
         ).encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        url, data=b"".join(parts), method="POST",
        headers={"xi-api-key": api_key,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:300]
        except Exception:  # noqa: BLE001 - best-effort detail only
            pass
        if e.code in (401, 403):
            raise RuntimeError(
                "ElevenLabs rejected the API key. Check Settings → Voice.") from e
        raise RuntimeError(
            f"ElevenLabs speech-to-text failed (HTTP {e.code}): {body}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(
            "Could not reach elevenlabs.io. Check the connection (this "
            "provider is cloud — local providers work offline).") from e


def _elevenlabs(audio: str | pathlib.Path, *, api_key: str = "",
                model: str = "", timeout: float = 45.0) -> str:
    if not api_key:
        raise RuntimeError(
            "ElevenLabs needs an API key. Set it in Settings → Voice first "
            "(audio is uploaded to the cloud in this mode).")
    src = pathlib.Path(audio)
    payload = src.read_bytes()
    ctype = "audio/webm" if src.suffix.lower() == ".webm" else "audio/wav"
    body = post_multipart(
        DEFAULT_ELEVENLABS_URL, api_key=api_key,
        filename=src.name or "clip.wav", content_type=ctype, data=payload,
        extra_fields={"model_id": model or DEFAULT_ELEVENLABS_MODEL},
        timeout=timeout)
    try:
        doc = json.loads(body.decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(
            "ElevenLabs returned an unexpected reply (still cloud — check "
            "your key and provider status).") from e
    return str(doc.get("text", "") or "").strip()


# ── Dispatch ─────────────────────────────────────────────────────────────

_HANDLERS = {
    LOCAL: _whisper,
    MOONSHINE: _moonshine,
    SYSTEM: _system,
    ELEVENLABS: _elevenlabs,
}


def transcribe(audio_path: str | pathlib.Path, *,
               provider: str = LOCAL, model: str = "",
               api_key: str = "", timeout: float = 45.0) -> str:
    """Transcribe one audio file with the chosen provider (see module doc)."""
    p = normalize(provider)
    handler = _HANDLERS[p]
    if not pathlib.Path(audio_path).exists():
        raise RuntimeError("The audio recording never reached the server.")
    return str(handler(audio_path, model=model, api_key=api_key,
                       timeout=timeout) or "").strip()


def provider_label(provider: str) -> str:
    """Human name for the Settings chips and health rows."""
    return {
        LOCAL: "Local Whisper",
        MOONSHINE: "Moonshine (local)",
        SYSTEM: "System speech",
        ELEVENLABS: "ElevenLabs (cloud)",
    }.get(normalize(provider) if provider else LOCAL, str(provider))


def cloud_label(provider: str) -> bool:
    """True when the chosen provider uploads audio off the machine."""
    return normalize(provider) in CLOUD_PROVIDERS


def backend_available(provider: str) -> bool:
    """Light check for the Settings page: is the backend importable?"""
    p = normalize(provider)
    if p == LOCAL:
        return _importable("faster_whisper")
    if p == MOONSHINE:
        return _importable("moonshine")
    if p == SYSTEM:
        return _importable("speech_recognition")
    return True  # cloud: reachable at use time


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False
