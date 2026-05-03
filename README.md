# InterviewAgent — AI Voice Interview Coach

An AI agent that conducts structured technical interviews end‑to‑end: generates tailored questions, runs the interview conversationally via voice, and produces a structured evaluation report with cited evidence.

## Features

- **Voice-based interviews** — questions are read aloud via TTS, answers recorded via browser mic
- **Tailored questions** — accepts job description and candidate profile to generate relevant questions
- **Adaptive conduct** — deep probes on strong answers, follow‑ups on weak ones, handles silence/off‑topic/clarification
- **Structured reports** — JSON evaluation with per‑skill scores, cited quotes, strengths/weaknesses, and hiring recommendation
- **Question caching** — same role+skills combo reuses questions for fair candidate comparison
- **Dashboard** — view all candidates, sessions, and detailed Q&A history

## Quick Start

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Set your API keys in .env
echo "OPENROUTER_API_KEY=your_key_here" > .env
echo "GROQ_API_KEY=your_key_here" >> .env

# Run
uvicorn backend.main:app --port 8000
```

Open **http://localhost:8000** in your browser.

## Architecture

Three separable components:

| Component | File | Role |
|-----------|------|------|
| **Generator** | `components/question_generator.py` | Generate tailored question sets |
| **Conductor** | `components/interview_conductor.py` | Adaptive interview state machine |
| **Evaluator** | `components/evaluator.py` | Score answers + structured reports |

See [WRITEUP.md](WRITEUP.md) for the full architecture document.
