"""
stt.py — Speech-to-Text using Groq's Whisper API (cloud, free tier)
No local model download. Audio is sent to Groq and transcript returned.
Free tier: 28,800 seconds/day (8 hours!)
Get key at: https://console.groq.com/
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL   = "whisper-large-v3-turbo"  # fast + accurate, free tier


def transcribe_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """
    Send audio bytes to Groq's Whisper API and return the transcript.
    suffix: file extension hint, e.g. '.webm', '.wav', '.mp3'
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not set in .env — get a free key at https://console.groq.com/"
        )

    # Map suffix to a mime type Groq accepts
    mime_map = {
        ".webm": "audio/webm",
        ".wav":  "audio/wav",
        ".mp3":  "audio/mpeg",
        ".ogg":  "audio/ogg",
        ".mp4":  "audio/mp4",
        ".m4a":  "audio/mp4",
        ".flac": "audio/flac",
    }
    mime = mime_map.get(suffix.lower(), "audio/webm")
    filename = f"audio{suffix}"

    resp = requests.post(
        GROQ_STT_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": (filename, audio_bytes, mime)},
        data={
            "model": GROQ_MODEL,
            "response_format": "json",
            "language": "en",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Groq STT error {resp.status_code}: {resp.text}")

    transcript = resp.json().get("text", "").strip()
    print(f"[STT] Groq transcript: {transcript!r}")
    return transcript
