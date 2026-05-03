"""
main.py — FastAPI application

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

import io
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from .interview import start_interview, process_answer, get_status
from .tts import text_to_speech_bytes
from .stt import transcribe_bytes
from . import store

app = FastAPI(title="Voice Interview Agent", version="1.0.0")

# Allow the frontend (served from file:// or any dev server) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class StartRequest(BaseModel):
    role: str
    skills: list[str]


class StartResponse(BaseModel):
    session_id: str
    question: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/session/start")
async def session_start(body: StartRequest):
    """
    Start a new interview session.
    Returns JSON with session_id + first question text,
    AND also returns the first question as MP3 audio via a separate field (base64).
    """
    if not body.role.strip():
        raise HTTPException(400, "role is required")
    if not body.skills:
        raise HTTPException(400, "at least one skill is required")

    session_id, question = start_interview(body.role.strip(), body.skills)

    # Convert question to audio
    audio_bytes = text_to_speech_bytes(question)
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()

    return {
        "session_id": session_id,
        "question": question,
        "audio_b64": audio_b64,
        "skill": store.get_session(session_id)["skills"][0],
    }


@app.post("/session/answer")
async def session_answer(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Submit a voice answer.
    Accepts multipart/form-data with:
      - session_id (str)
      - audio (file: .webm / .wav / .mp3)

    Returns JSON with evaluation + next question text + audio.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "complete":
        raise HTTPException(400, "Interview already complete")

    # Read uploaded audio
    audio_bytes = await audio.read()
    suffix = "." + (audio.filename or "audio.webm").rsplit(".", 1)[-1]

    # STT
    transcript = transcribe_bytes(audio_bytes, suffix=suffix)
    if not transcript:
        transcript = "[no speech detected]"

    # Process answer through state machine
    result = process_answer(session_id, transcript)

    # TTS for next question (if any)
    next_audio_b64 = None
    if result["next_question"]:
        next_audio_bytes = text_to_speech_bytes(result["next_question"])
        import base64
        next_audio_b64 = base64.b64encode(next_audio_bytes).decode()

    return {
        **result,
        "next_audio_b64": next_audio_b64,
    }


@app.get("/session/status/{session_id}")
def session_status(session_id: str):
    return get_status(session_id)


@app.post("/session/end/{session_id}")
def session_end(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    history = session.get("history", [])
    store.delete_session(session_id)
    return {"message": "Session ended", "history": history}
