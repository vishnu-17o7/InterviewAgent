"""
llm.py — OpenRouter LLM integration

Uses nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free for audio-capable calls
(the model accepts audio input directly — no separate STT needed).

Falls back to a free text-only model for pure text tasks (question generation,
summary) to stay within rate limits.
"""

import os
import json
import re
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Audio-capable model (free) — used when we need to process voice input
AUDIO_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

# Text-only model (free) — used for question generation, summaries, etc.
TEXT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


def _call_llm(messages: list[dict], temperature: float = 0.7, model: str | None = None) -> str:
    """
    Send messages to OpenRouter and return the assistant text.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    use_model = model or TEXT_MODEL

    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "InterviewAgent",
        },
        json={
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _build_audio_content(text_prompt: str, audio_b64: str, audio_format: str = "wav") -> list[dict]:
    """
    Build the multimodal content array with text + audio for the user message.
    """
    return [
        {"type": "text", "text": text_prompt},
        {
            "type": "input_audio",
            "input_audio": {
                "data": audio_b64,
                "format": audio_format,
            },
        },
    ]


# ── Question Generation (text-only, no audio needed) ──────────────────────

def generate_question(role: str, skill: str, history: list[dict]) -> str:
    """
    Generate an interview question for the given skill.
    """
    history_text = ""
    if history:
        history_text = "\n\nPrevious questions already asked:\n" + "\n".join(
            f"- {h['question']}" for h in history
        )

    system = (
        f"You are an expert technical interviewer conducting a job interview for the role of {role}. "
        "Ask one clear, concise interview question. Do NOT include any preamble or labels — "
        "only output the question itself."
    )
    user = (
        f"Ask me a focused interview question about: {skill}.{history_text}\n\n"
        "Output ONLY the question, nothing else."
    )
    return _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


# ── Skills Suggestion ────────────────────────────────────────────────────

def suggest_skills(role: str) -> list[str]:
    """
    Ask the LLM for 5 relevant interview skills for the given role.
    """
    system = (
        "You are an expert technical recruiter. "
        "Given a job role, suggest exactly 5 relevant technical skills "
        "that would be tested in a technical interview. "
        "Output ONLY a JSON array of 5 strings. No preamble."
    )
    user = (
        f"Role: {role}\n\n"
        "Output exactly 5 skills as a JSON array of strings. Example:\n"
        '["Python", "System Design", "Django", "REST APIs", "SQL"]'
    )

    raw = _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.7)

    import json as _json
    import re as _re

    match = _re.search(r'\[.*\]', raw, _re.DOTALL)
    if match:
        try:
            parsed = _json.loads(match.group())
            if isinstance(parsed, list) and len(parsed) >= 1:
                return [str(s) for s in parsed[:5]]
        except (_json.JSONDecodeError, ValueError):
            pass

    return ["Communication", "Problem Solving", "Technical Knowledge", "Teamwork", "Adaptability"]


# ── Bulk Question Generation (text-only) ────────────────────────────────

QUESTIONS_PER_SKILL = 5


def generate_all_questions(role: str, skills: list[str]) -> list[dict]:
    """
    Generate QUESTIONS_PER_SKILL questions for each skill.
    Returns [{"skill": str, "question_text": str}, ...]
    """
    skills_list = ", ".join(skills)
    system = (
        f"You are an expert technical interviewer conducting a job interview for the role of {role}. "
        f"Generate exactly {QUESTIONS_PER_SKILL} clear, concise interview questions for each skill listed. "
        f"That means {len(skills) * QUESTIONS_PER_SKILL} total questions. "
        "Output ONLY a JSON array of objects with keys 'skill' and 'question'. "
        "No preamble, no numbering, no extra text."
    )
    user = (
        f"Generate {QUESTIONS_PER_SKILL} interview questions for each of these skills: {skills_list}.\n\n"
        f"That is {len(skills) * QUESTIONS_PER_SKILL} total questions.\n"
        "Output ONLY a JSON array like:\n"
        '[{"skill": "Python", "question": "..."}, {"skill": "Python", "question": "..."}, ...]\n'
        "Respond with valid JSON only."
    )

    raw = _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.7)

    import json as _json
    import re as _re

    match = _re.search(r'\[.*\]', raw, _re.DOTALL)
    if match:
        try:
            parsed = _json.loads(match.group())
            return [
                {"skill": item.get("skill", ""),
                 "question_text": item.get("question", "")}
                for item in parsed
            ]
        except (_json.JSONDecodeError, ValueError):
            pass

    # Fallback: generate one at a time
    result = []
    for skill in skills:
        for _ in range(QUESTIONS_PER_SKILL):
            q = generate_question(role, skill, [])
            result.append({"skill": skill, "question_text": q})
    return result


# ── Follow-up Generation (text-only) ──────────────────────────────────────

def generate_followup(role: str, skill: str, question: str, answer: str) -> str:
    """
    Generate a follow-up question when the candidate's answer is weak.
    """
    system = (
        f"You are an expert technical interviewer for {role}. "
        "The candidate gave a weak or incomplete answer. Ask one focused follow-up question "
        "to probe deeper. Output ONLY the question."
    )
    user = (
        f"Skill: {skill}\n"
        f"Original question: {question}\n"
        f"Candidate answer: {answer}\n\n"
        "Ask a follow-up question. Output ONLY the question."
    )
    return _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


# ── Evaluate Answer WITH Audio (audio-capable model) ──────────────────────

def evaluate_answer_with_audio(
    role: str,
    skill: str,
    question: str,
    audio_b64: str,
    audio_format: str = "wav",
) -> dict:
    """
    Send the candidate's voice audio directly to the audio-capable LLM.
    The model will listen to the audio and evaluate the answer.
    Returns {transcript: str, score: int 1-10, feedback: str}.
    """
    system = (
        f"You are an expert technical interviewer evaluating a candidate for the role of {role}. "
        f"The candidate was asked about '{skill}'.\n\n"
        f"The interview question was: \"{question}\"\n\n"
        "The candidate's spoken answer is provided as audio. "
        "Listen to the audio carefully, then:\n"
        "1. Transcribe what the candidate said.\n"
        "2. Score the answer from 1 to 10.\n"
        "3. Provide concise feedback (1-2 sentences).\n\n"
        'Respond ONLY in this exact JSON format:\n'
        '{"transcript": "<what they said>", "score": <int>, "feedback": "<string>"}'
    )

    user_content = _build_audio_content(
        text_prompt=(
            f"Listen to my spoken answer to this interview question about {skill}:\n"
            f'"{question}"\n\n'
            "Transcribe my answer, score it 1-10, and give feedback. Respond in JSON only."
        ),
        audio_b64=audio_b64,
        audio_format=audio_format,
    )

    raw = _call_llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        model=AUDIO_MODEL,
    )

    # Parse JSON safely
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return {
                "transcript": parsed.get("transcript", ""),
                "score": int(parsed.get("score", 5)),
                "feedback": parsed.get("feedback", raw),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback — couldn't parse JSON
    return {"transcript": raw, "score": 5, "feedback": raw}


# ── Evaluate Answer from Text (fallback, text-only model) ─────────────────

def evaluate_answer(role: str, skill: str, question: str, answer: str) -> dict:
    """
    Evaluate the candidate's answer (text-only fallback).
    Returns {score: int 1-10, feedback: str}.
    """
    system = (
        f"You are an expert technical interviewer evaluating a candidate for {role}. "
        "Score the answer from 1 to 10 and give concise feedback (1-2 sentences). "
        'Respond ONLY in this exact JSON format: {"score": <int>, "feedback": "<string>"}'
    )
    user = (
        f"Skill: {skill}\n"
        f"Question: {question}\n"
        f"Candidate answer: {answer}\n\n"
        "Evaluate and respond in JSON."
    )
    raw = _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.3)

    # Parse JSON safely
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fallback
    return {"score": 5, "feedback": raw}


# ── Summary (text-only) ───────────────────────────────────────────────────

def generate_summary(role: str, history: list[dict]) -> str:
    """
    Generate a final interview summary after all questions.
    """
    qa_text = "\n\n".join(
        f"Q: {h['question']}\nA: {h['answer']}\nScore: {h['score']}/10\nFeedback: {h['feedback']}"
        for h in history
    )
    system = (
        f"You are an expert interviewer summarising a completed interview for {role}. "
        "Give an overall assessment: strengths, weaknesses, and a hiring recommendation. "
        "Keep it under 150 words."
    )
    user = f"Interview transcript:\n\n{qa_text}\n\nProvide the summary."
    return _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
