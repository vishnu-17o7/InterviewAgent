"""
stt.py — Speech-to-Text using faster-whisper (local, free)
Model is loaded once at startup (lazy singleton).
"""

import io
import tempfile
import os
from faster_whisper import WhisperModel

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print("[STT] Loading faster-whisper base model (first load may take a moment)...")
        _model = WhisperModel("base", device="cpu", compute_type="int8")
        print("[STT] Model loaded.")
    return _model


def transcribe_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """
    Transcribe audio from raw bytes.
    suffix should match the audio format: .webm, .wav, .mp3, etc.
    Returns the transcribed text string.
    """
    model = _get_model()

    # Write to a temp file because faster-whisper needs a file path
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[STT] Detected language: {info.language} | Transcript: {text!r}")
        return text
    finally:
        os.unlink(tmp_path)
