# Voice Interview Agent — Project Report

**Repository:** [https://github.com/vishnu-17o7/InterviewAgent](https://github.com/vishnu-17o7/InterviewAgent)

---

## 1. Overview

A voice-first AI interview agent that conducts realistic technical interviews. Candidates speak their answers; the system transcribes, evaluates, and generates structured reports with cited evidence.

**Two modes:**
- **Gemini Live** — Real-time voice-to-voice via Google Gemini Live API (bidirectional audio streaming, interruptions supported)
- **Legacy** — TTS playback + browser recording + upload to backend for evaluation via OpenRouter

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Vanilla JS SPA)             │
│  index.html  ──  app.js  ──  gemini-live.js                 │
│  Sections: Landing → Setup → Interview → Summary → Dashboard │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                     Backend (FastAPI)                        │
│                                                              │
│  main.py          — Routes, CORS, config                     │
│  interview.py     — Adaptive interview state machine         │
│  llm.py           — OpenRouter integration, all prompts      │
│  db.py            — SQLite schema + CRUD                     │
│  store.py         — Thin wrapper over db                     │
│  tts.py           — gTTS text-to-speech                      │
│                                                              │
│  components/                                                 │
│    question_generator.py   — Extracted question gen logic    │
│    interview_conductor.py  — Extracted adaptive flow logic   │
│    evaluator.py            — Extracted scoring/report logic  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   SQLite    │
                    │ candidates  │
                    │ job_templ.  │
                    │ questions   │
                    │ sessions    │
                    │ answers     │
                    └─────────────┘
```

---

## 3. Key Features

| Feature | Details |
|---------|---------|
| Voice-to-voice (Gemini Live) | Bidirectional audio, real-time transcription + evaluation |
| Verbal-only questions | No "write a function" — all questions are spoken/conceptual |
| Job description awareness | JD + candidate profile tailor all questions |
| Adaptive conduct | Score thresholds trigger: deep probe (≥8), follow-up (<6), re-ask (silence), rephrase (clarification), redirect (off-topic) |
| Structured reports | JSON output: strengths, weaknesses, cited quotes, skill breakdown, recommendation |
| Anti-coaching guardrail | Injected into every prompt — never hints at correct answer |
| Question caching | Role + skills combo hashed, cached in SQLite for fair evaluation |
| Dashboard | All candidates, sessions, scores with accordion drill-down |
| Configurable port | `PORT` env var in `.env` |
| Test suite | 3 test files with full LLM integration tests |

---

## 4. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/config` | Client config (Gemini key, mode flag) |
| `POST` | `/candidate/register` | Register candidate by name |
| `GET` | `/candidate/{id}/sessions` | List candidate sessions |
| `POST` | `/skills/suggest` | Suggest 5 skills for a role |
| `POST` | `/session/start` | Start interview (role, skills, JD, profile) |
| `POST` | `/session/answer` | Submit audio answer (legacy mode) |
| `GET` | `/session/next-question/{id}` | Get current question (Gemini Live mode) |
| `POST` | `/session/submit-transcript/{id}` | Submit transcript + score (Gemini Live mode) |
| `GET` | `/session/status/{id}` | Get session state |
| `POST` | `/session/end/{id}` | End interview early |
| `GET` | `/dashboard/overview` | Dashboard stats + candidate list |

---

## 5. Database Schema

- **candidates** — `id, name, created_at`
- **job_templates** — `id, role, skills_json, jd, profile, question_hash`
- **questions** — `id, job_template_id, skill, question_text, pool_index`
- **sessions** — `id, candidate_id, job_template_id, status, question_index, created_at, completed_at`
- **session_answers** — `id, session_id, question, answer, score, feedback, skill, question_index, follow_up_count, action_type, created_at`

---

## 6. Question Flow (Gemini Live Mode)

1. Backend generates 10 questions (2 skills × 5 each) via OpenRouter
2. Frontend fetches question from `/session/next-question`
3. Gemini Live reads question aloud, candidate speaks answer
4. Gemini transcribes + scores (1-10) + gives feedback
5. Frontend submits to `/session/submit-transcript`
6. Backend records answer, applies adaptive logic:
   - Score ≥ 8 → deep probe (one additional harder question)
   - Score < 6 → follow-up question
   - Silence → re-ask
   - Clarification → rephrase
   - Off-topic → redirect
7. After 10 questions → generate structured report

---

## 7. .env Configuration

```
OPENROUTER_API_KEY=sk-or-...    # Question generation + reports
GROQ_API_KEY=gsk_...            # Fallback LLM
GEMINI_API_KEY=AIza...          # Voice-to-voice audio
USE_GEMINI_LIVE=true            # true = Gemini Live, false = legacy TTS+record
PORT=8003                       # Server port
```

---

## 8. Running Locally

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Configure .env with your API keys

# Start server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8003

# Open http://127.0.0.1:8003
```

---

## 9. Tests

```bash
pytest backend/tests/test_api.py -v              # All endpoints
pytest backend/tests/test_adaptive_conduct.py -v # Edge cases
pytest backend/tests/test_interview_flow.py -v   # Full lifecycle
```

Tests use real LLM calls (OpenRouter key required) with isolated SQLite databases.

---

## 10. Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLite |
| LLMs | OpenRouter (OpenAI/Anthropic models), Groq |
| Voice (Gemini Live) | Google Gemini 2.5 Flash Live API |
| Voice (Legacy) | gTTS + browser MediaRecorder |
| Frontend | Vanilla JS, CSS Grid/Flexbox |
| Testing | pytest, httpx, FastAPI TestClient |
| Version Control | Git, GitHub (public) |

---

## 11. Key Design Decisions

- **Question caching by role+skills hash** — Same role/skills combo reuses questions for fair comparison across candidates
- **Round-robin skill selection** — `question_index % num_skills` cycles through skills evenly
- **10-question fixed length** — Follow-ups and deep probes count toward the total, preventing infinite loops
- **Anti-coaching in every prompt** — Guardrail injected at system prompt level, not post-filtered
- **Structured JSON reports** — Replaced narrative summaries with parseable JSON (strengths, weaknesses, cited quotes)
