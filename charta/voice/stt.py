"""Local speech-to-text behind one interface (faster-whisper default)."""
from __future__ import annotations

import pathlib


def transcribe(audio_path: str | pathlib.Path, model: str = "small") -> str:
    """Transcribe local audio file. Raises friendly error if backend missing."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "Voice backend not installed. Run: pip install faster-whisper "
            "(local, default). Cloud ElevenLabs stays opt-in only.") from e
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _ = m.transcribe(str(audio_path))
    return " ".join(s.text for s in segments).strip()


CLOUD_NOTICE = ("ElevenLabs speech-to-text is CLOUD: audio leaves your device. "
                "It is off by default and requires opt-in.")

# ── Moonshine (tiny, 80 MB) ─────────────────────────────────────────────
try:
    import moonshine
    _MOONSHINE_AVAILABLE = True
except ImportError:  # noqa: BLE001
    _MOONSHINE_AVAILABLE = False
def transcribe_moonshine(audio_path: str | pathlib.Path) -> str:
    """Transcribe with Moonshine. Raises if not installed."""
    if not _MOONSHINE_AVAILABLE:
        raise RuntimeError("moonshine is not installed. pip install moonshine")
    result = moonshine.transcribe(str(audio_path))
    return str(result.get("text", "")).strip()
# ── ElevenLabs (cloud) ──────────────────────────────────────────────────
try:
    import urllib.request
    _ELEVENLABS_AVAILABLE = True
except ImportError:  # noqa: BLE001
    _ELEVENLABS_AVAILABLE = False
def transcribe_elevenlabs(audio_path: str | pathlib.Path, api_key: str) -> str:
    """Upload to ElevenLabs and return the transcript."""
    if not _ELEVENLABS_AVAILABLE:
        raise RuntimeError("elevenlabs is not installed")
    with open(str(audio_path), "rb") as f:
        audio_bytes = f.read()
    payload = {
        "audio_base64": base64.b64encode(audio_bytes).decode(),
    }
    url = "https://api.elevenlabs.io/v1/text‑speech"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return data.get("text", "").strip()