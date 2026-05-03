"""
store.py — Thin wrapper around db.py for session management.
"""

from . import db


def register_candidate(name: str) -> dict:
    return db.register_candidate(name)


def find_or_create_job_template(role: str, skills: list[str]) -> int:
    return db.find_or_create_job_template(role, skills)


def job_template_has_questions(job_template_id: int) -> bool:
    return db.job_template_has_questions(job_template_id)


def insert_questions(job_template_id: int, questions: list[dict]):
    db.insert_questions(job_template_id, questions)


def get_questions_for_job(job_template_id: int) -> list[dict]:
    return db.get_questions_for_job(job_template_id)


def create_session(candidate_id: int, job_template_id: int, skills: list[str], first_question: str, job_description: str = "", candidate_profile: str = "") -> str:
    return db.create_session(candidate_id, job_template_id, skills, first_question, job_description, candidate_profile)


def get_session(session_id: str) -> dict | None:
    return db.get_session(session_id)


def update_session(session_id: str, updates: dict):
    db.update_session(session_id, updates)


def append_history(session_id: str, entry: dict):
    db.append_history(session_id, entry)


def delete_session(session_id: str):
    db.delete_session(session_id)


def get_candidate_sessions(candidate_id: int) -> list[dict]:
    return db.get_candidate_sessions(candidate_id)
