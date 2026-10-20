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
