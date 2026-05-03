"""
Component 3: Evaluation & Report Generation

Interface:
  evaluate_answer(role, skill, question, answer) -> {"score": int, "feedback": str}
  evaluate_answer_audio(role, skill, question, audio_b64, format) -> {"transcript": str, "score": int, "feedback": str}
  generate_report(role, history, jd, profile) -> dict

Responsibilities:
- Scores individual answers 1-10 with concise feedback
- Transcribes audio answers via the LLM
- Generates a structured JSON evaluation report with cited evidence
- Does NOT control interview flow or generate questions
"""

from .. import llm


def evaluate_answer(role: str, skill: str, question: str, answer: str) -> dict:
    return llm.evaluate_answer(role, skill, question, answer)


def evaluate_answer_audio(role: str, skill: str, question: str,
                          audio_b64: str, audio_format: str = "wav") -> dict:
    return llm.evaluate_answer_with_audio(role, skill, question, audio_b64, audio_format)


def generate_report(role: str, history: list[dict], job_description: str = "",
                    candidate_profile: str = "") -> dict:
    return llm.generate_structured_report(role, history, job_description, candidate_profile)
