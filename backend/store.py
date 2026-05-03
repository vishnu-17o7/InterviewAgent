"""
store.py — In-memory session store
Each session is a dict keyed by session_id (UUID string).
"""

import uuid
from typing import Optional

# sessions: { session_id: SessionData }
sessions: dict[str, dict] = {}


def create_session(role: str, skills: list[str]) -> str:
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "session_id": session_id,
        "role": role,
        "skills": skills,
        "skill_index": 0,           # which skill we are on
        "follow_up_count": 0,       # follow-ups asked for current skill
        "history": [],              # list of {question, answer, score, feedback}
        "status": "active",         # active | complete
        "current_question": None,
    }
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    return sessions.get(session_id)


def update_session(session_id: str, updates: dict) -> None:
    if session_id in sessions:
        sessions[session_id].update(updates)


def append_history(session_id: str, entry: dict) -> None:
    if session_id in sessions:
        sessions[session_id]["history"].append(entry)


def delete_session(session_id: str) -> None:
    sessions.pop(session_id, None)
