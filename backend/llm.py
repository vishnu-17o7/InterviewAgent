"""
llm.py — OpenRouter LLM integration (deepseek/deepseek-chat, free tier)
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-chat-v3-0324:free"


def _call_llm(messages: list[dict], temperature: float = 0.7) -> str:
    """
    Send messages to OpenRouter and return the assistant text.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "InterviewAgent",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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


def evaluate_answer(role: str, skill: str, question: str, answer: str) -> dict:
    """
    Evaluate the candidate's answer. Returns {score: int 1-10, feedback: str}.
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
    import json, re
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fallback
    return {"score": 5, "feedback": raw}


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
