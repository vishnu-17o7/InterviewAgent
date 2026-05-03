# InterviewAgent — Component Separation

## Architecture Overview

The system is divided into three independent components, each with a clear interface. They communicate through shared data models (Python dicts) rather than direct imports, making any component swappable without affecting the others.

```
┌─────────────────────┐
│  FastAPI Routes      │  (main.py) — thin HTTP layer
└──────┬──────┬───────┘
       │      │
       ▼      ▼
┌──────────┐ ┌──────────────────┐ ┌─────────────────┐
│ Generator│ │ Conductor         │ │ Evaluator        │
│          │ │                   │ │                  │
│ generate │ │ next_action()     │ │ evaluate_answer()│
│ suggest  │ │ pick_question()   │ │ generate_report()│
└────┬─────┘ └────────┬──────────┘ └────────┬─────────┘
     │                │                     │
     └────────────────┼─────────────────────┘
                      │
              ┌───────▼────────┐
              │  LLM Client     │  (llm.py) — shared OpenRouter API calls
              │  Database       │  (db.py)  — SQLite persistence
              └────────────────┘
```

---

## Component 1: Question Generator (`question_generator.py`)

**Interface:**
```python
generate(role, skills, job_description, candidate_profile) -> list[dict]
suggest_skills(role) -> list[str]
```

**Responsibility:** Accepts a job description and candidate profile to produce a tailored question set. Caches questions per role+skills combo in the database so multiple candidates for the same role get identical questions for fair evaluation.

**Independence:** Does not know about interview flow, scoring, or the UI. Could be swapped for a static question bank, a different LLM, or a rules-based generator without affecting anything else.

---

## Component 2: Interview Conductor (`interview_conductor.py`)

**Interface:**
```python
next_action(session, transcript, score) -> Action
```

**Responsibility:** Controls the adaptive interview flow. Decides the next action based on the candidate's response:
- **Score >= 8**: Deep probe — ask a harder follow-up
- **Score < 6**: Weak follow-up — probe for gaps
- **Silence / no speech**: Re-ask the question
- **Clarification request**: Rephrase without coaching
- **Off-topic answer**: Redirect back to the question
- **Otherwise**: Advance to the next question (round-robin across skills, 10 total)

**Independence:** Does not generate questions or evaluate answers. It only decides *what kind* of next step to take. The actual question text comes from the Generator, and scores come from the Evaluator.

---

## Component 3: Evaluator (`evaluator.py`)

**Interface:**
```python
evaluate_answer(role, skill, question, answer) -> {"score": int, "feedback": str}
evaluate_answer_audio(role, skill, question, audio_b64, format) -> {...}
generate_report(role, history, job_description, candidate_profile) -> dict
```

**Responsibility:** Scores answers and produces structured evaluation reports. The report includes:
- Overall score and hiring recommendation (Advance / Borderline / Decline)
- Strengths and weaknesses with cited evidence
- Per-skill breakdown with avg scores and question counts
- Notable quotes from the candidate
- Follow-up suggestions for the next round

**Independence:** Does not control the interview or generate questions. The report format is a JSON object (not a narrative blob), making it machine-readable and embeddable in other systems.

---

## Anti-Coaching Guardrail

All prompts include this system instruction:

> CRITICAL: You must NEVER hint at, suggest, or lead the candidate toward a correct answer. When clarifying a question, rephrase it differently but do NOT reveal what you are looking for. Do not confirm or deny whether an answer is correct. Remain neutral.

This is centrally defined in `llm.py` as `ANTI_COACHING` and injected into every evaluation and follow-up prompt.

---

## Design Decisions

1. **SQLite over Postgres/MySQL** — Zero-setup, single-file, no external service. Sufficient for a local tool.
2. **10 questions per interview** — Balances thoroughness with candidate fatigue. Fixed count ensures fair comparison.
3. **Round-robin skill selection** — Prevents skill bias. A candidate strong in Python won't get 7 Python questions while only getting 3 System Design questions.
4. **Question caching by role+skills** — Multiple candidates for the same role see identical questions. This is critical for fair evaluation.
5. **Audio sent directly to the LLM** — No separate STT step. The LLM transcribes AND scores in one call, reducing latency and cost.
6. **gTTS for question audio** — Free, offline-capable TTS. Questions are read aloud for accessibility and realism.
