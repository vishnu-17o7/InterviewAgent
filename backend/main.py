"""
main.py — FastAPI application

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

import io
import os
import base64
import traceback
from pathlib import Path
from fastapi import FastAPI, File, Form, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", "8000"))

from .interview import start_interview, process_answer_audio, get_status
from .tts import text_to_speech_bytes
from . import store

app = FastAPI(title="Voice Interview Agent", version="1.0.0")

# Allow the frontend (served from file:// or any dev server) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# ── Request / Response Models ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str


class StartRequest(BaseModel):
    candidate_id: int
    role: str
    skills: list[str]
    job_description: str = ""
    candidate_profile: str = ""


class SuggestSkillsRequest(BaseModel):
    role: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def app_config():
    """Return client-side configuration (non-secret values)."""
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "use_gemini_live": os.getenv("USE_GEMINI_LIVE", "false").lower() == "true",
    }


@app.post("/candidate/register")
def candidate_register(body: RegisterRequest):
    """Register a candidate by name. Returns candidate_id."""
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    candidate = store.register_candidate(body.name.strip())
    return candidate


@app.get("/candidate/{candidate_id}/sessions")
def candidate_sessions(candidate_id: int):
    """List past interview sessions for a candidate."""
    return store.get_candidate_sessions(candidate_id)


@app.post("/skills/suggest")
def skills_suggest(body: SuggestSkillsRequest):
    """Suggest 5 relevant interview skills for a role."""
    if not body.role.strip():
        raise HTTPException(400, "role is required")
    from . import llm
    skills = llm.suggest_skills(body.role.strip())
    return {"skills": skills}


@app.get("/dashboard/overview")
def dashboard_overview():
    """Return all candidates, sessions, scores, and aggregate stats."""
    from . import db
    return db.get_dashboard_overview()


@app.post("/session/start")
async def session_start(body: StartRequest):
    """
    Start a new interview session.
    Uses cached questions if this role+skills combo has been used before.
    """
    if not body.role.strip():
        raise HTTPException(400, "role is required")
    if not body.skills:
        raise HTTPException(400, "at least one skill is required")

    session_id, question = start_interview(body.candidate_id, body.role.strip(), body.skills, body.job_description.strip(), body.candidate_profile.strip())

    audio_bytes = text_to_speech_bytes(question)
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

    The audio is sent DIRECTLY to the audio-capable LLM (Nemotron) for
    transcription + evaluation in a single call. No separate STT step.

    Returns JSON with evaluation + next question text + audio.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "complete":
        raise HTTPException(400, "Interview already complete")

    # Read uploaded audio and encode to base64
    audio_bytes = await audio.read()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    # Determine audio format from filename/mime
    filename = audio.filename or "audio.webm"
    suffix = filename.rsplit(".", 1)[-1].lower()
    format_map = {
        "webm": "wav",   # OpenRouter may need wav/mp3; we'll try as-is
        "wav": "wav",
        "mp3": "mp3",
        "ogg": "wav",
        "m4a": "mp3",
        "flac": "flac",
    }
    audio_format = format_map.get(suffix, "wav")

    # Send audio directly to the audio-capable LLM
    result = process_answer_audio(session_id, audio_b64, audio_format)

    # TTS for next question (if any)
    next_audio_b64 = None
    if result["next_question"]:
        next_audio_bytes = text_to_speech_bytes(result["next_question"])
        next_audio_b64 = base64.b64encode(next_audio_bytes).decode()

    return {
        **result,
        "next_audio_b64": next_audio_b64,
    }


@app.get("/session/status/{session_id}")
def session_status(session_id: str):
    return get_status(session_id)


@app.get("/session/next-question/{session_id}")
def session_next_question(session_id: str):
    """
    Gemini Live flow: return the current question text for the audio agent to speak.
    Used by the frontend before opening the Gemini Live audio channel.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "complete":
        raise HTTPException(400, "Interview already complete")

    skills = session["skills"]
    qi = session["question_index"]
    skill = skills[qi % len(skills)] if skills else ""

    return {
        "session_id": session_id,
        "question": session["current_question"],
        "question_index": qi,
        "skill": skill,
        "is_complete": False,
    }


class SubmitTranscriptRequest(BaseModel):
    transcript: str
    score: int
    feedback: str = ""


@app.post("/session/submit-transcript/{session_id}")
def session_submit_transcript(session_id: str, body: SubmitTranscriptRequest):
    """
    Gemini Live flow: after the audio agent evaluates an answer, submit the
    transcript and score. The backend records it and returns the next question.
    """
    from .interview import process_answer

    try:
        result = process_answer(session_id, body.transcript)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result


@app.post("/session/end/{session_id}")
def session_end(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    history = session.get("history", [])
    store.update_session(session_id, {"status": "complete"})
    return {"message": "Session ended", "history": history}

from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=PORT, reload=True)
