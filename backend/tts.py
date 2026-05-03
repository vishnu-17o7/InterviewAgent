"""
tts.py — Text-to-Speech using gTTS
Returns MP3 bytes (no disk writes, no os.system calls).
"""

import io
from gtts import gTTS


def text_to_speech_bytes(text: str, lang: str = "en") -> bytes:
    """
    Convert text to speech and return raw MP3 bytes.
    The caller is responsible for streaming these bytes to the client.
    """
    tts = gTTS(text=text, lang=lang, slow=False)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()
